"""ASGI middleware that authenticates WebSocket upgrades and resolves the
tenant before the consumer runs.

The browser/Flutter clients open `ws(s)://<tenant>.example.com/ws/notifications/?token=<access>`.
We must mirror the REST-side logic that lives in
`TenantMainMiddleware` (host → tenant) and `TenantJWTAuthentication`
(token → user, with token-schema must equal request-schema).
"""

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django_tenants.utils import (
    get_tenant_domain_model,
    get_tenant_model,
    schema_context,
)
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

logger = logging.getLogger("notifications")
User = get_user_model()


def _extract_host(scope) -> str:
    """Channels passes headers as a list of (bytes, bytes) tuples."""
    for key, value in scope.get("headers", []):
        if key == b"host":
            return value.decode("latin-1").lower()
    return ""


def _extract_token(scope) -> str:
    raw = scope.get("query_string", b"")
    if isinstance(raw, bytes):
        raw = raw.decode("latin-1")
    return (parse_qs(raw).get("token") or [""])[0]


@database_sync_to_async
def _resolve_tenant(host: str):
    """Look up the tenant by its registered domain.

    Mirrors what TenantMainMiddleware does for HTTP requests. The host on the
    incoming WS scope is e.g. `pruthvi.localhost:8000` — django-tenants stores
    domains without the port, so we strip it.
    """
    if not host:
        return None
    hostname = host.split(":")[0]
    DomainModel = get_tenant_domain_model()
    try:
        return DomainModel.objects.select_related("tenant").get(
            domain=hostname,
        ).tenant
    except DomainModel.DoesNotExist:
        return None


@database_sync_to_async
def _resolve_user(schema_name: str, user_id):
    """Look up the user inside the tenant schema.

    `UserModel` lives in SHARED_APPS so the row physically sits in the public
    schema, but routing every query through `schema_context` keeps any
    related-object access (e.g. branch_profile) tenant-correct.
    """
    if not schema_name or not user_id:
        return AnonymousUser()
    with schema_context(schema_name):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return AnonymousUser()


class TenantJWTAuthMiddleware(BaseMiddleware):
    """Authenticate the WS scope using a simplejwt access token from the
    query string. Reject the connection if any of these fail:

      * No or invalid token
      * Token's `schema_name` claim missing or doesn't match the request host
      * Tenant has no active subscription
      * User does not exist or is inactive
    """

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()
        scope["tenant"] = None
        scope["schema_name"] = None

        token = _extract_token(scope)
        if not token:
            return await super().__call__(scope, receive, send)

        try:
            validated = UntypedToken(token)
        except (InvalidToken, TokenError) as exc:
            logger.info("WS auth: invalid token (%s)", exc)
            return await super().__call__(scope, receive, send)

        token_schema = validated.get("schema_name") or ""
        user_id = validated.get("user_id")

        host = _extract_host(scope)
        tenant = await _resolve_tenant(host)

        if tenant is None:
            logger.info("WS auth: no tenant for host %s", host)
            return await super().__call__(scope, receive, send)

        if token_schema and token_schema != tenant.schema_name:
            logger.info(
                "WS auth: token schema %s != request schema %s",
                token_schema,
                tenant.schema_name,
            )
            return await super().__call__(scope, receive, send)

        if not getattr(tenant, "has_active_subscription", True):
            logger.info("WS auth: tenant %s not active", tenant.schema_name)
            return await super().__call__(scope, receive, send)

        user = await _resolve_user(tenant.schema_name, user_id)
        if user.is_anonymous:
            return await super().__call__(scope, receive, send)

        scope["user"] = user
        scope["tenant"] = tenant
        scope["schema_name"] = tenant.schema_name
        return await super().__call__(scope, receive, send)


def TenantJWTAuthMiddlewareStack(inner):
    """Wrapper kept for symmetry with `AuthMiddlewareStack`."""
    return TenantJWTAuthMiddleware(inner)
