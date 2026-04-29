from django.db import connection
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class TenantJWTAuthentication(JWTAuthentication):
    """
    JWT auth for django-tenants.

    Tenant selection happens before authentication in TenantMainMiddleware.
    The token must belong to the same schema as the current request host.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        request_schema = getattr(connection, "schema_name", "public")
        token_schema = token.get("schema_name")
        tenant = getattr(request, "tenant", None)

        if token_schema and token_schema != request_schema:
            raise AuthenticationFailed("Token tenant does not match request tenant.")

        if request_schema != "public":
            if tenant is None:
                raise AuthenticationFailed("Tenant not resolved for request.")
            if not getattr(tenant, "has_active_subscription", True):
                raise AuthenticationFailed("Tenant subscription is not active.")

        user._active_tenant = tenant if request_schema != "public" else None
        request.tenant = tenant
        return user, token
