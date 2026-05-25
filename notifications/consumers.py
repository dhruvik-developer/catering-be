import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django_tenants.utils import schema_context

from .models import Notification

logger = logging.getLogger("notifications")


def group_name_for(schema_name: str, user_id) -> str:
    """Channel group naming is tenant-scoped so a notification published from
    one tenant can never fan out to a socket connected on another tenant's
    host, even in the unlikely event of a UUID collision."""
    return f"t_{schema_name}_u_{user_id}"


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """One connection per authenticated user-device.

    Outbound frames (server → client):
      - {"type": "connection.ready", "unread_count": N}
      - {"type": "notification", "id": ..., "title": ..., ..., "unread_count": N}
      - {"type": "unread_count", "unread_count": N}
      - {"type": "pong"}

    Inbound frames (client → server) — kept tiny on purpose:
      - {"type": "ping"}
      - {"type": "mark_read", "notification_id": <int>}
    """

    async def connect(self):
        user = self.scope.get("user")
        schema_name = self.scope.get("schema_name")
        if user is None or user.is_anonymous or not schema_name:
            await self.close(code=4401)
            return

        self.user = user
        self.schema_name = schema_name
        self.group_name = group_name_for(schema_name, user.pk)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        unread = await self._unread_count()
        await self.send_json(
            {"type": "connection.ready", "unread_count": unread}
        )

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type") if isinstance(content, dict) else None
        if msg_type == "ping":
            await self.send_json({"type": "pong"})
            return
        if msg_type == "mark_read":
            notif_id = content.get("notification_id")
            if isinstance(notif_id, int):
                await self._mark_read(notif_id)
                unread = await self._unread_count()
                await self.send_json(
                    {"type": "unread_count", "unread_count": unread}
                )
            return
        # Anything else is silently dropped — keeps the client→server
        # surface area small so a misbehaving client can't push us off-script.

    # group_send dispatches to this handler. `event["payload"]` is the JSON
    # frame the client should see; we just forward it.
    async def notification_message(self, event):
        await self.send_json(event["payload"])

    # ───────── db helpers (per-tenant) ─────────
    @database_sync_to_async
    def _unread_count(self):
        with schema_context(self.schema_name):
            return Notification.objects.filter(
                recipient=self.user, is_read=False
            ).count()

    @database_sync_to_async
    def _mark_read(self, notif_id):
        with schema_context(self.schema_name):
            Notification.objects.filter(
                pk=notif_id, recipient=self.user, is_read=False
            ).update(is_read=True)
