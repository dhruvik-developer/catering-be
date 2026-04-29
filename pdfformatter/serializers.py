from rest_framework import serializers

from .models import PdfFormatter


class PdfFormatterSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = PdfFormatter
        fields = [
            "id",
            "name",
            "code",
            "description",
            "html_content",
            "sample_data",
            "is_default",
            "is_active",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_html_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("HTML content is required.")
        return value

    def validate_sample_data(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Sample data must be a JSON object.")
        return value
