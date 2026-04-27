from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from user.models import Tenant
from user.tenanting import activate_schema, normalize_schema_name, reset_schema


class TenantJWTAuthentication(JWTAuthentication):
    """
    JWT auth that activates the customer's PostgreSQL schema for the request.

    Platform superusers normally stay in the public schema. They can inspect a
    tenant schema by sending X-Tenant-Schema: <schema_name>.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            reset_schema()
            request.tenant = None
            return None

        user, token = result
        tenant = getattr(user, "tenant", None)
        requested_schema = request.headers.get("X-Tenant-Schema")

        if user.is_superuser and requested_schema:
            try:
                schema_name = normalize_schema_name(requested_schema)
            except ValueError as exc:
                raise AuthenticationFailed(str(exc)) from exc

            tenant = Tenant.objects.filter(schema_name=schema_name).first()
            if tenant is None:
                raise AuthenticationFailed("Tenant schema not found.")

        if tenant is None:
            reset_schema()
            request.tenant = None
            return user, token

        if not user.is_superuser and not tenant.has_active_subscription:
            raise AuthenticationFailed("Tenant subscription is not active.")

        activate_schema(tenant.schema_name)
        request.tenant = tenant
        return user, token
