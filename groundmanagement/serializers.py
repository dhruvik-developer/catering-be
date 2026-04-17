from rest_framework import serializers

from .models import (
    EventGroundRequirement,
    GroundCategory,
    GroundChecklistTemplate,
    GroundChecklistTemplateItem,
    GroundItem,
)


class GroundCategorySerializer(serializers.ModelSerializer):
    ground_items = serializers.SerializerMethodField()

    class Meta:
        model = GroundCategory
        fields = ["id", "name", "description", "is_active", "ground_items"]

    def get_ground_items(self, obj):
        items_qs = obj.ground_items.all().order_by("name")
        return GroundItemSerializer(items_qs, many=True).data


class GroundItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = GroundItem
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "unit",
            "description",
            "is_active",
        ]


class GroundChecklistTemplateItemSerializer(serializers.ModelSerializer):
    ground_item_name = serializers.CharField(source="ground_item.name", read_only=True)

    class Meta:
        model = GroundChecklistTemplateItem
        fields = [
            "id",
            "ground_item",
            "ground_item_name",
            "required_quantity",
            "is_required",
        ]


class GroundChecklistTemplateSerializer(serializers.ModelSerializer):
    template_items = GroundChecklistTemplateItemSerializer(many=True, read_only=True)

    class Meta:
        model = GroundChecklistTemplate
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "is_default",
            "template_items",
        ]


class EventGroundRequirementSerializer(serializers.ModelSerializer):
    ground_item_name = serializers.CharField(source="ground_item.name", read_only=True)
    category_id = serializers.IntegerField(source="ground_item.category.id", read_only=True)
    category_name = serializers.CharField(source="ground_item.category.name", read_only=True)
    unit = serializers.CharField(source="ground_item.unit", read_only=True)

    class Meta:
        model = EventGroundRequirement
        fields = [
            "id",
            "event_booking",
            "event_session",
            "ground_item",
            "ground_item_name",
            "category_id",
            "category_name",
            "unit",
            "required_quantity",
            "arranged_quantity",
            "is_required",
            "is_arranged",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        event_booking = attrs.get("event_booking") or getattr(
            self.instance, "event_booking", None
        )
        event_session = attrs.get("event_session") or getattr(
            self.instance, "event_session", None
        )

        if event_booking and event_session and event_session.booking_id != event_booking.id:
            raise serializers.ValidationError(
                {"event_session": "Selected session does not belong to selected booking."}
            )

        required_quantity = attrs.get(
            "required_quantity",
            getattr(self.instance, "required_quantity", 0),
        )
        arranged_quantity = attrs.get(
            "arranged_quantity",
            getattr(self.instance, "arranged_quantity", 0),
        )
        is_required = attrs.get("is_required", getattr(self.instance, "is_required", True))

        if required_quantity < 0 or arranged_quantity < 0:
            raise serializers.ValidationError("Quantities cannot be negative.")

        attrs["is_arranged"] = bool(
            is_required and arranged_quantity >= required_quantity 
        )
        return attrs
