from django.conf import settings
from django.db import models
from django.utils import timezone


class DeviceToken(models.Model):
    """One row per (user, device) FCM registration. A single user can have
    several active devices (Android phone, iPad, web browser) and every one
    should receive push when the app is closed/backgrounded."""

    PLATFORM_ANDROID = "android"
    PLATFORM_IOS = "ios"
    PLATFORM_WEB = "web"
    PLATFORM_CHOICES = (
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_WEB, "Web"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    # FCM tokens are ~163 chars today but Google has bumped the length in the
    # past — TextField avoids future migration churn.
    fcm_token = models.TextField(unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    device_id = models.CharField(max_length=128, blank=True, default="")
    app_version = models.CharField(max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_device_token"
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user_id}/{self.platform}/{self.fcm_token[:12]}…"

    def touch(self):
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])


class Notification(models.Model):
    """Persisted notification. Every WebSocket frame the client receives also
    has a row here so the unread badge survives a reconnect and the user can
    open the history screen and see past notifications."""

    TYPE_EVENT_ASSIGNED = "event_assigned"
    TYPE_EVENT_UPDATED = "event_updated"
    TYPE_EVENT_CANCELLED = "event_cancelled"
    # Admin-facing response alerts. Fired when an assigned staff member or
    # vendor accepts/declines from the mobile app, so the catering owner sees
    # the action in the Alerts dropdown without polling the order page.
    TYPE_STAFF_RESPONSE = "staff_response"
    TYPE_VENDOR_ASSIGNED = "vendor_assigned"
    TYPE_VENDOR_RESPONSE = "vendor_response"
    TYPE_GENERIC = "generic"
    TYPE_CHOICES = (
        (TYPE_EVENT_ASSIGNED, "Event assigned"),
        (TYPE_EVENT_UPDATED, "Event updated"),
        (TYPE_EVENT_CANCELLED, "Event cancelled"),
        (TYPE_STAFF_RESPONSE, "Staff response"),
        (TYPE_VENDOR_ASSIGNED, "Vendor assigned"),
        (TYPE_VENDOR_RESPONSE, "Vendor response"),
        (TYPE_GENERIC, "Generic"),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
        default=TYPE_GENERIC,
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    # Deep-link payload — opaque JSON so the client can route to any screen.
    # Shape used by the Flutter/React clients today:
    #   {"route": "/event-bookings/detail", "event_id": 12, "session_id": 5}
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.recipient_id}: {self.title}"

    def mark_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])
