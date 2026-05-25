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
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

from notifications.middleware import TenantJWTAuthMiddlewareStack  # noqa: E402
from notifications.routing import websocket_urlpatterns  # noqa: E402

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            TenantJWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
