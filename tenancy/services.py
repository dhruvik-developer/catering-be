from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import tenant_context


def create_tenant_admin_user(tenant, admin_data):
    if not admin_data:
        return None

    with tenant_context(tenant):
        if getattr(connection, "schema_name", "public") != tenant.schema_name:
            raise RuntimeError("Tenant admin user creation did not enter tenant schema.")

        username = admin_data["username"]
        UserModel = get_user_model()
        if UserModel.objects.filter(username=username).exists():
            raise ValueError("Username already exists in this tenant.")

        return UserModel.objects.create_user(
            username=username,
            email=admin_data.get("email", ""),
            password=admin_data["password"],
            first_name=admin_data.get("first_name", ""),
            last_name=admin_data.get("last_name", ""),
            is_staff=True,
            is_superuser=admin_data.get("is_superuser", False),
        )
