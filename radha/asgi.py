"""ASGI config for Radhika project.

Daphne (catering-ws.sh) runs against this application and terminates
WebSocket upgrades. HTTP traffic continues to go through gunicorn against
`radha.wsgi:application`.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "radha.settings")

# Initialise Django BEFORE importing anything that touches the ORM. The
# Channels imports below pull in the user app via the JWT middleware.
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

from notifications.middleware import TenantJWTAuthMiddlewareStack  # noqa: E402
from notifications.routing import websocket_urlpatterns  # noqa: E402

django_asgi_app = get_asgi_application()


class _MobileFriendlyOriginValidator(OriginValidator):
    """Origin validator that doesn't reject Origin-less connections.

    Channels' stock `AllowedHostsOriginValidator` rejects any WS handshake
    whose Origin header is missing — but Flutter's dart:io WebSocketChannel
    and many other non-browser clients never send Origin. The browser WS
    still gets a strict check (it always sends Origin), so cross-origin
    abuse from a malicious tab is still blocked; only the `Origin: null`
    case is allowed through so the catering mobile app can connect.

    Auth is still enforced downstream by `TenantJWTAuthMiddleware` — without
    a valid tenant-scoped JWT the consumer closes with 4401 anyway, so
    relaxing Origin doesn't open the socket to anonymous traffic.
    """

    def __init__(self, application):
        # Lazily pull ALLOWED_HOSTS off settings (matches what the stock
        # AllowedHostsOriginValidator does). In DEBUG mode with no hosts
        # set, fall back to "*" so local dev never silently rejects.
        allowed = list(settings.ALLOWED_HOSTS or [])
        if settings.DEBUG and not allowed:
            allowed = ["*"]
        super().__init__(application, allowed)

    def valid_origin(self, parsed_origin):
        # Mobile clients (Flutter dart:io, native iOS, etc.) skip Origin.
        # Treat that as "trusted, no origin to validate" — the JWT layer
        # still enforces tenant scope, so this isn't a security gap.
        if parsed_origin is None:
            return True
        return self.validate_origin(parsed_origin)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": _MobileFriendlyOriginValidator(
            TenantJWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
