from rest_framework import serializers

from .models import DeviceToken, Notification


class DeviceTokenSerializer(serializers.ModelSerializer):
    # Override the auto-generated `fcm_token` field so it does NOT carry the
    # default UniqueValidator that DRF derives from `unique=True`. The view
    # does an upsert via `update_or_create`, so the same token re-arriving
    # from another tab / after re-login is expected, not an error.
    fcm_token = serializers.CharField(
        max_length=4096,
        allow_blank=False,
        trim_whitespace=False,
    )

    class Meta:
        model = DeviceToken
        fields = ["id", "fcm_token", "platform", "device_id", "app_version"]
        read_only_fields = ["id"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "message",
            "data",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields
