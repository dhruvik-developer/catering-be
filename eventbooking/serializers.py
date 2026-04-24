from rest_framework import serializers
from .models import *
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from decimal import Decimal, InvalidOperation


class EventItemConfigSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    session_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = EventItemConfig
        fields = [
            "id", 
            "event", 
            "session", 
            "session_id",
            "item_name", 
            "is_vendor_supplied", 
            "vendor", 
            "vendor_name",
            "quantity",
            "unit",
            "calculated_from_persons",
            "created_at"
        ]
        read_only_fields = ["created_at"]


class IngredientVendorAssignmentSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    session_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = IngredientVendorAssignment
        fields = [
            "id",
            "ingredient",
            "ingredient_name",
            "vendor",
            "vendor_name",
            "event",
            "session",
            "session_id",
            "source_type",
            "created_at",
        ]
        read_only_fields = ["created_at"]

class EventSessionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    session_id = serializers.IntegerField(source="id", read_only=True)
    event_date = serializers.DateField(
        input_formats=["%d-%m-%Y"],  # Accept DD-MM-YYYY in the payload
        format="%d-%m-%Y",  # Return DD-MM-YYYY in the response
    )
    managers_assigned = serializers.SerializerMethodField()
    summoned_staff_details = serializers.SerializerMethodField()
    ground_management = serializers.JSONField(required=False, write_only=True)
    outsourced_items = serializers.JSONField(required=False, default=list)
    order_local_ingredients = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = EventSession
        fields = [
            "id",
            "session_id",
            "event_date",
            "event_time",
            "event_address",
            "per_dish_amount",
            "estimated_persons",
            "selected_items",
            "extra_service_amount",
            "extra_service",
            "waiter_service_amount",
            "waiter_service",
            "managers_assigned",
            "summoned_staff_details",
            "assigned_vendors",
            "outsourced_items",
            "order_local_ingredients",
            "ground_management",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["ground_management"] = self.get_ground_management(instance)
        return data

    def get_managers_assigned(self, obj):
        managers = []
        for assignment in obj.staff_assignments.all():
            role_name = (
                assignment.role_at_event.name
                if assignment.role_at_event
                else (assignment.staff.role.name if assignment.staff.role else "")
            )
            if role_name.lower() == "manager" or assignment.staff.staff_type == "Fixed":
                managers.append(
                    {
                        "assignment_id": assignment.id,
                        "name": assignment.staff.name,
                        "staff_type": assignment.staff.staff_type,
                        "people_summoned": assignment.number_of_persons,
                        "role": role_name,
                    }
                )
        return managers

    def get_summoned_staff_details(self, obj):
        summoned_staff = []
        for assignment in obj.staff_assignments.all():
            role_name = (
                assignment.role_at_event.name
                if assignment.role_at_event
                else (assignment.staff.role.name if assignment.staff.role else "")
            )
            if assignment.staff.staff_type in ["Agency", "Contract"]:
                summoned_staff.append(
                    {
                        "assignment_id": assignment.id,
                        "name": assignment.staff.name,
                        "staff_type": assignment.staff.staff_type,
                        "people_summoned": assignment.number_of_persons,
                        "role": role_name,
                    }
                )
        return summoned_staff

    def get_ground_management(self, obj):
        grouped = defaultdict(list)
        requirements = obj.ground_requirements.select_related(
            "ground_item", "ground_item__category"
        ).all()
        for req in requirements:
            grouped[req.ground_item.category.name].append(
                {
                    "name": req.ground_item.name,
                    "unit": req.ground_item.unit,
                    "quantity": str(req.required_quantity),
                    "arranged_quantity": str(req.arranged_quantity),
                    "is_required": req.is_required,
                    "is_arranged": req.is_arranged,
                    "notes": req.notes or "",
                }
            )
        return dict(grouped)


class EventBookingSerializer(serializers.ModelSerializer):
    advance_amount = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    advance_payment_mode = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    date = serializers.DateField(
        format="%d-%m-%Y", read_only=True  # Format for response
    )
    sessions = EventSessionSerializer(many=True, required=False)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = EventBooking
        fields = [
            "id",  # Include the primary key for reference
            "name",
            "mobile_no",
            "date",
            "reference",
            "status",
            "advance_amount",
            "advance_payment_mode",
            "description",
            "rule",
            "sessions",
            "created_by",
            "created_by_username",
        ]
        read_only_fields = ["created_by", "created_by_username"]

    def create(self, validated_data):
        sessions_data = validated_data.pop("sessions", [])
        booking = EventBooking.objects.create(**validated_data)
        for session_data in sessions_data:
            ground_management = session_data.pop("ground_management", None)
            session = EventSession.objects.create(booking=booking, **session_data)
            self._sync_ground_management(booking, session, ground_management)
        return booking

    def update(self, instance, validated_data):
        sessions_data = validated_data.pop("sessions", None)

        # update regular booking fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # If sessions were provided in update, we overwrite old sessions
        if sessions_data is not None:
            existing_sessions = {s.id: s for s in instance.sessions.all()}

            for session_data in sessions_data:
                session_id = session_data.get("id", None)
                ground_management = session_data.pop("ground_management", None)
                if session_id and session_id in existing_sessions:
                    # Update existing session
                    session = existing_sessions.pop(session_id)
                    for attr, value in session_data.items():
                        setattr(session, attr, value)
                    session.save()
                    self._sync_ground_management(instance, session, ground_management)
                else:
                    # Create new session if no valid ID
                    session = EventSession.objects.create(booking=instance, **session_data)
                    self._sync_ground_management(instance, session, ground_management)

            # Delete sessions that were not in the PUT payload
            for session in existing_sessions.values():
                session.delete()

        return instance

    def _sync_ground_management(self, booking, session, payload):
        if not payload or not isinstance(payload, dict):
            return

        from groundmanagement.models import (
            EventGroundRequirement,
            GroundCategory,
            GroundItem,
        )

        for category_name, items in payload.items():
            if not isinstance(items, list):
                continue

            category = GroundCategory.objects.filter(name=category_name).first()
            if not category:
                continue

            for item_data in items:
                if not isinstance(item_data, dict):
                    continue

                item_name = item_data.get("name")
                if not item_name:
                    continue

                ground_item = GroundItem.objects.filter(
                    category=category, name=item_name
                ).first()
                if not ground_item:
                    continue

                quantity_raw = item_data.get("quantity", 0)
                arranged_raw = item_data.get("arranged_quantity", 0)

                try:
                    required_quantity = Decimal(str(quantity_raw or 0))
                except (InvalidOperation, TypeError, ValueError):
                    required_quantity = Decimal("0")

                try:
                    arranged_quantity = Decimal(str(arranged_raw or 0))
                except (InvalidOperation, TypeError, ValueError):
                    arranged_quantity = Decimal("0")

                is_required = item_data.get("is_required", True)
                notes = item_data.get("notes", "")

                EventGroundRequirement.objects.update_or_create(
                    event_booking=booking,
                    event_session=session,
                    ground_item=ground_item,
                    defaults={
                        "required_quantity": required_quantity,
                        "arranged_quantity": arranged_quantity,
                        "is_required": bool(is_required),
                        "notes": notes,
                    },
                )
