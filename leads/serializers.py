import re

from rest_framework import serializers

from .models import Lead


PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,20}$")


class PublicLeadSerializer(serializers.ModelSerializer):
    """Serializer used by the public POST /api/public/contact endpoint.

    Locks down which fields the unauthenticated caller can write.
    """

    class Meta:
        model = Lead
        fields = ["full_name", "email", "phone", "company", "message", "source"]
        extra_kwargs = {
            "source": {"required": False},
        }

    def validate_full_name(self, value):
        value = (value or "").strip()
        if len(value) < 2:
            raise serializers.ValidationError("Please enter your full name.")
        return value

    def validate_message(self, value):
        value = (value or "").strip()
        if len(value) < 5:
            raise serializers.ValidationError("Message is too short.")
        return value

    def validate_phone(self, value):
        value = (value or "").strip()
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Please enter a valid phone number.")
        return value

    def validate_source(self, value):
        return (value or "").strip() or "website"


class AdminLeadSerializer(serializers.ModelSerializer):
    """Serializer for admin list/detail/update."""

    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )

    class Meta:
        model = Lead
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "company",
            "message",
            "source",
            "status",
            "status_display",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "company",
            "message",
            "source",
            "created_at",
            "updated_at",
        ]

    def validate_status(self, value):
        valid = {choice[0] for choice in Lead.STATUS_CHOICES}
        if value not in valid:
            raise serializers.ValidationError("Invalid status.")
        return value
