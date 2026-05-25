"""Side-effects that auto-fire notifications.

Add new receivers here when more places in the app need to notify users —
keeps the trigger surface in one searchable file.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from eventstaff.models import EventStaffAssignment

from .models import Notification
from .services import NotificationService

logger = logging.getLogger("notifications")


@receiver(post_save, sender=EventStaffAssignment)
def on_event_staff_assigned(sender, instance, created, **kwargs):
    """Fire a notification when a staff member is freshly assigned to a session.

    The staff member only has an app to receive on if they were given a login
    account (`Staff.user_account`). Contract / agency rows without a user
    account are silently skipped — they get notified by other means (phone).
    """
    if not created:
        return

    staff = instance.staff
    user = getattr(staff, "user_account", None)
    if user is None or not user.is_active:
        return

    session = instance.session
    booking = getattr(session, "booking", None) if session else None
    booking_name = booking.name if booking else "an event"
    event_date = session.event_date if session else None
    date_label = event_date.strftime("%d %b %Y") if event_date else ""

    message = f"You have been assigned to {booking_name}"
    if date_label:
        message = f"{message} on {date_label}."
    else:
        message = f"{message}."

    NotificationService.notify_user(
        user,
        notification_type=Notification.TYPE_EVENT_ASSIGNED,
        title="New Event Assigned",
        message=message,
        data={
            "route": "/event-bookings/detail",
            "event_id": booking.id if booking else None,
            "session_id": session.id if session else None,
            "assignment_id": instance.id,
        },
    )
