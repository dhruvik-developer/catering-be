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

class EventVendorAssignmentSerializer(serializers.ModelSerializer):
    """Wire shape for the vendor-side workflow row. Used both standalone
    (`/event-vendor-assignments/...`) and nested under `EventSession.vendor_assignments`
    so the Flutter app can render Accept/Decline + dispatch state without
    a follow-up round-trip."""

    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    vendor_mobile = serializers.CharField(source="vendor.mobile_no", read_only=True)
    booking_id = serializers.IntegerField(source="session.booking_id", read_only=True)
    booking_name = serializers.CharField(source="session.booking.name", read_only=True)
    event_date = serializers.DateField(
        source="session.event_date", read_only=True, format="%d-%m-%Y"
    )
    event_time = serializers.CharField(source="session.event_time", read_only=True)
    event_address = serializers.CharField(source="session.event_address", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = EventVendorAssignment
        fields = (
            "id",
            "session_id",
            "booking_id",
            "booking_name",
            "event_date",
            "event_time",
            "event_address",
            "vendor",
            "vendor_name",
            "vendor_mobile",
            "response_status",
            "decline_reason",
            "responded_at",
            "declined_item_keys",
            "driver_name",
            "driver_phone",
            "driver_eta",
            "dispatched_at",
            "is_mine",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_is_mine(self, obj):
        request = self.context.get("request") if hasattr(self, "context") else None
        if request is None or not getattr(request.user, "is_authenticated", False):
            return False
        vendor_user_id = getattr(obj.vendor, "user_account_id", None)
        return bool(vendor_user_id) and vendor_user_id == request.user.id


class EventSessionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    session_id = serializers.IntegerField(source="id", read_only=True)
    event_date = serializers.DateField(
        input_formats=["%d-%m-%Y"],  # Accept DD-MM-YYYY in the payload
        format="%d-%m-%Y",  # Return DD-MM-YYYY in the response
    )
    managers_assigned = serializers.SerializerMethodField()
    summoned_staff_details = serializers.SerializerMethodField()
    vendor_assignments = serializers.SerializerMethodField()
    my_vendor_assignment = serializers.SerializerMethodField()
    checklist_ticks = serializers.SerializerMethodField()
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
            "vendor_assignments",
            "my_vendor_assignment",
            "checklist_ticks",
            "assigned_vendors",
            "outsourced_items",
            "order_local_ingredients",
            "ground_management",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["ground_management"] = self.get_ground_management(instance)
        return data

    # Mirrors `_ASSIGNED_TO_ME_TRUTHY` in eventbooking/views.py — duplicated
    # here so the serializer can decide whether the request is the "assignee"
    # view (mobile / staff portal) without importing from views.
    _ASSIGNEE_VIEW_VALUES = frozenset({"1", "true", "yes", "on", "me"})

    def _is_assignee_view(self, request):
        if request is None:
            return False
        raw = request.query_params.get("assigned_to_me", "")
        return str(raw).strip().lower() in self._ASSIGNEE_VIEW_VALUES

    def _should_hide_from_assignee(self, assignment, request):
        """True when this row should disappear from the staff-portal view.

        Single hide rule now: the viewer's own declined row drops out of
        their own UI so it doesn't clutter their day-to-day list — admins
        still see it (no `assigned_to_me` flag) with the reason so they
        can reassign.

        EVERY other assignment on the booking — fellow managers, supply
        agencies, contract staff — stays visible so the assigned team can
        coordinate (who's accepted, who declined, who hasn't responded
        yet). Privacy of decline-reasons across managers was the original
        reason for hiding non-mine rows, but real-world feedback from the
        catering team is that this hurts coordination more than it helps."""
        if not self._is_assignee_view(request):
            return False

        viewer_id = (
            request.user.id
            if getattr(request.user, "is_authenticated", False)
            else None
        )
        staff_user_id = getattr(assignment.staff, "user_account_id", None)
        is_mine = bool(staff_user_id) and staff_user_id == viewer_id

        # Hide my own declined row — cleanup only. Everything else stays.
        if is_mine and assignment.response_status == "declined":
            return True
        return False

    def _assignment_payload(self, assignment, role_name):
        """Shared shape for managers_assigned / summoned_staff_details. Adds
        the staff response workflow fields (status, decline reason, history)
        and an `is_mine` flag so the mobile app can show Accept/Decline only
        for assignments owned by the current user."""
        request = self.context.get("request") if hasattr(self, "context") else None
        viewer_id = (
            request.user.id
            if request is not None and getattr(request.user, "is_authenticated", False)
            else None
        )
        staff_user_id = getattr(assignment.staff, "user_account_id", None)

        history = [
            {
                "id": entry.id,
                "response": entry.response,
                "reason": entry.reason or "",
                "responded_by_id": entry.responded_by_id,
                "responded_by_username": (
                    entry.responded_by.username if entry.responded_by_id else None
                ),
                "responded_at": entry.responded_at,
            }
            for entry in assignment.response_history.all()
        ]

        return {
            "assignment_id": assignment.id,
            "name": assignment.staff.name,
            "staff_id": assignment.staff_id,
            "staff_type": assignment.staff.staff_type,
            "people_summoned": assignment.number_of_persons,
            "role": role_name,
            # Service category for waiter-type staff (VIP / VVIP / Normal / …).
            # Lets the agency / contract portal show which grade of people to
            # send. Empty string when the staff record has no waiter type.
            "waiter_type": (
                assignment.staff.waiter_type.name
                if assignment.staff.waiter_type
                else ""
            ),
            # Response workflow
            "response_status": assignment.response_status,
            "decline_reason": assignment.decline_reason or "",
            "responded_at": assignment.responded_at,
            "is_mine": bool(staff_user_id) and staff_user_id == viewer_id,
            "response_history": history,
            # True when the staff/manager has a linked login user_account —
            # i.e. they can actually accept/decline from the mobile app.
            # Without a login, response_status sits at its "pending" default
            # forever (since there's no one to flip it), so the React admin
            # uses this flag to suppress the misleading status chip.
            "has_user_account": bool(staff_user_id),
        }

    def get_managers_assigned(self, obj):
        request = self.context.get("request") if hasattr(self, "context") else None
        managers = []
        assignments = obj.staff_assignments.select_related(
            "staff",
            "staff__user_account",
            "role_at_event",
            "staff__role",
            "staff__waiter_type",
        ).prefetch_related("response_history__responded_by")
        for assignment in assignments:
            if self._should_hide_from_assignee(assignment, request):
                continue
            role_name = (
                assignment.role_at_event.name
                if assignment.role_at_event
                else (assignment.staff.role.name if assignment.staff.role else "")
            )
            if role_name.lower() == "manager" or assignment.staff.staff_type == "Fixed":
                managers.append(self._assignment_payload(assignment, role_name))
        return managers

    def get_summoned_staff_details(self, obj):
        request = self.context.get("request") if hasattr(self, "context") else None
        summoned_staff = []
        assignments = obj.staff_assignments.select_related(
            "staff",
            "staff__user_account",
            "role_at_event",
            "staff__role",
            "staff__waiter_type",
        ).prefetch_related("response_history__responded_by")
        for assignment in assignments:
            if self._should_hide_from_assignee(assignment, request):
                continue
            role_name = (
                assignment.role_at_event.name
                if assignment.role_at_event
                else (assignment.staff.role.name if assignment.staff.role else "")
            )
            if assignment.staff.staff_type in ["Agency", "Contract"]:
                summoned_staff.append(self._assignment_payload(assignment, role_name))
        return summoned_staff

    def get_vendor_assignments(self, obj):
        """Every vendor row on the session. Admins and staff/receivers see
        all of them (they need driver info + per-item declines to plan the
        receive). The list is restricted only when the viewer themselves is
        a vendor — that's the one case where we don't want one vendor seeing
        another vendor's decline reason or driver phone."""
        request = self.context.get("request") if hasattr(self, "context") else None
        qs = obj.vendor_assignments.select_related("vendor", "vendor__user_account")
        if self._is_assignee_view(request) and request is not None:
            user = request.user
            if getattr(user, "is_authenticated", False) and (
                hasattr(user, "vendor_profile") and user.vendor_profile is not None
            ):
                qs = qs.filter(vendor__user_account=user)
        return EventVendorAssignmentSerializer(
            qs, many=True, context=self.context
        ).data

    def get_checklist_ticks(self, obj):
        """Every checklist tick row on the session — `received`, `delivered`,
        `rejected`, etc. Surfaced here so both staff and vendor portals can
        render the right per-item chip without a second round-trip. The
        Flutter side already has a dedicated checklist fetcher for the
        screen that toggles ticks; this is for the read-only banner state
        on the session detail."""
        ticks = obj.checklist_ticks.all()
        return [
            {
                "item_key": t.item_key,
                "action": t.action,
                "is_done": t.is_done,
                "notes": t.notes or "",
                "ticked_at": t.ticked_at,
            }
            for t in ticks
        ]

    def get_my_vendor_assignment(self, obj):
        """Shortcut for the mobile vendor portal: the single row owned by
        the logged-in vendor, or None. Saves the client a flatten step."""
        request = self.context.get("request") if hasattr(self, "context") else None
        if request is None or not getattr(request.user, "is_authenticated", False):
            return None
        user = request.user
        if not (hasattr(user, "vendor_profile") and user.vendor_profile is not None):
            return None
        row = (
            obj.vendor_assignments.select_related(
                "vendor", "vendor__user_account"
            )
            .filter(vendor__user_account=user)
            .first()
        )
        if row is None:
            return None
        return EventVendorAssignmentSerializer(row, context=self.context).data

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
            "branch_profile",
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
        read_only_fields = ["branch_profile", "created_by", "created_by_username"]

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

            category = GroundCategory.objects.filter(
                branch_profile=booking.branch_profile,
                name=category_name,
            ).first()
            if not category:
                continue

            for item_data in items:
                if not isinstance(item_data, dict):
                    continue

                item_name = item_data.get("name")
                if not item_name:
                    continue

                ground_item = GroundItem.objects.filter(
                    branch_profile=booking.branch_profile,
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


from .models import SessionChecklistTick


class SessionChecklistTickSerializer(serializers.ModelSerializer):
    ticked_by_username = serializers.CharField(
        source="ticked_by.username", read_only=True
    )

    class Meta:
        model = SessionChecklistTick
        fields = (
            "id",
            "item_key",
            "action",
            "is_done",
            "notes",
            "ticked_by_username",
            "ticked_at",
        )
        read_only_fields = ("id", "ticked_by_username", "ticked_at")
