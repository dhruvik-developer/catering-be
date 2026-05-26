"""Central notification entry point.

Anywhere in the codebase that wants to notify a user goes through
`NotificationService.notify_user(...)`. The service:

  1. Persists a `Notification` row (history + unread badge survive disconnect).
  2. Pushes a frame to the user's tenant-scoped channel group (live clients).
  3. Schedules a thread-pool job to fan out via FCM (offline clients).

All three steps happen post-commit so a long-running outer transaction
can't race the consumer's read.
"""

import atexit
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django_tenants.utils import schema_context

from . import fcm
from .consumers import group_name_for
from .models import DeviceToken, Notification

logger = logging.getLogger("notifications")
User = get_user_model()

# A small shared executor so a burst of notifications doesn't spawn a fresh
# thread each time. `max_workers=4` is plenty when Google's API responds in
# 200-500ms — at 5 calls/sec sustained throughput we still have headroom.
_FCM_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="notif-fcm",
)
atexit.register(lambda: _FCM_EXECUTOR.shutdown(wait=False, cancel_futures=False))


def iter_admin_recipients(branch_profile_id=None):
    """Yield the admin users who should receive a tenant-wide alert.

    Resolution rules — mirror the same scoping the rest of the codebase uses
    for branch-aware permissions:
      - Every `main_admin` user is always included (they oversee all
        branches).
      - `branch_admin` users are included only when their branch matches
        `branch_profile_id`. If the caller doesn't know the branch (None),
        every branch_admin is yielded so we don't silently miss anyone.

    Inactive users are skipped so an offboarded admin doesn't keep getting
    pushes on a stale FCM token. The caller stays inside the tenant schema —
    this helper just reads; it doesn't open a schema_context of its own.
    """
    qs = User.objects.filter(is_active=True, is_staff=True)
    main = qs.filter(branch_role="main_admin")
    branch = qs.filter(branch_role="branch_admin")
    if branch_profile_id is not None:
        branch = branch.filter(branch_profile_id=branch_profile_id)
    # Distinct on id to defend against the unlikely case where someone
    # configured a user with both roles via a future schema change.
    seen = set()
    for user in list(main) + list(branch):
        if user.id in seen:
            continue
        seen.add(user.id)
        yield user


def _current_schema_name() -> str:
    """Reads the tenant schema the calling code is currently inside.

    For requests routed through `TenantMainMiddleware` this is the tenant's
    schema; from a `schema_context(...)` block it's whatever that block
    activated. Defaults to "public" so misuse from a shared-schema context
    fails loudly rather than silently writing to the wrong tenant.
    """
    return getattr(connection, "schema_name", "public")


class NotificationService:
    """The ONLY way the rest of the codebase should create a notification."""

    @classmethod
    def notify_user(
        cls,
        user,
        *,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Notification]:
        if user is None or not getattr(user, "is_active", False):
            return None

        schema_name = _current_schema_name()
        if schema_name == "public":
            # Notifications live in tenant schemas; refusing here surfaces
            # accidental misuse instead of writing the row to public.
            logger.warning(
                "NotificationService called from public schema; "
                "wrap the call in schema_context() with the target tenant."
            )
            return None

        payload_data = dict(data or {})

        notif = Notification.objects.create(
            recipient=user,
            notification_type=notification_type,
            title=title,
            message=message,
            data=payload_data,
        )

        # Run side-effects after the surrounding transaction commits so a
        # consumer that wakes on the WS frame doesn't query for a row that
        # hasn't been flushed yet.
        transaction.on_commit(
            lambda: cls._dispatch(schema_name, notif.id)
        )
        return notif

    # ───────── internals ─────────
    @classmethod
    def _dispatch(cls, schema_name: str, notification_id: int) -> None:
        try:
            cls._push_ws(schema_name, notification_id)
        except Exception:
            logger.exception(
                "WS push failed for notification %s (schema=%s)",
                notification_id,
                schema_name,
            )
        # FCM happens in the background; even if the WS push raised, every
        # offline device still gets a chance to be notified.
        _FCM_EXECUTOR.submit(cls._fcm_safe, schema_name, notification_id)

    @classmethod
    def _push_ws(cls, schema_name: str, notification_id: int) -> None:
        with schema_context(schema_name):
            notif = Notification.objects.get(pk=notification_id)
            unread = Notification.objects.filter(
                recipient_id=notif.recipient_id, is_read=False
            ).count()

        payload = {
            "type": "notification",
            "id": notif.id,
            "notification_type": notif.notification_type,
            "title": notif.title,
            "message": notif.message,
            "data": notif.data,
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat(),
            "unread_count": unread,
        }
        layer = get_channel_layer()
        if layer is None:
            logger.warning("No channel layer configured; skipping WS push")
            return
        async_to_sync(layer.group_send)(
            group_name_for(schema_name, notif.recipient_id),
            {"type": "notification.message", "payload": payload},
        )

    @classmethod
    def _fcm_safe(cls, schema_name: str, notification_id: int) -> None:
        try:
            cls._fcm(schema_name, notification_id)
        except Exception:
            logger.exception(
                "FCM dispatch failed for notification %s (schema=%s)",
                notification_id,
                schema_name,
            )

    @classmethod
    def _fcm(cls, schema_name: str, notification_id: int) -> None:
        with schema_context(schema_name):
            try:
                notif = Notification.objects.select_related("recipient").get(
                    pk=notification_id
                )
            except Notification.DoesNotExist:
                return
            tokens = list(
                DeviceToken.objects.filter(
                    user=notif.recipient, is_active=True
                ).values_list("fcm_token", flat=True)
            )
            if not tokens:
                return

            data_payload = {
                **(notif.data or {}),
                "notification_id": notif.id,
                "notification_type": notif.notification_type,
            }

            # FCM multicast caps at 500 tokens per call — page through if a
            # user somehow has more.
            invalid_tokens: list[str] = []
            for chunk_start in range(0, len(tokens), 500):
                chunk = tokens[chunk_start:chunk_start + 500]
                invalid_tokens.extend(
                    fcm.send_multicast(
                        chunk,
                        title=notif.title,
                        body=notif.message,
                        data=data_payload,
                    )
                )

            if invalid_tokens:
                DeviceToken.objects.filter(
                    fcm_token__in=invalid_tokens
                ).update(is_active=False)
                logger.info(
                    "Deactivated %s invalid FCM tokens",
                    len(invalid_tokens),
                )
