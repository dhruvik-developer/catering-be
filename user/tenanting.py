import re
from contextlib import contextmanager

from django.db import connection
from django.utils.text import slugify

try:
    from django_tenants.utils import schema_context as tenant_schema_context
except Exception:  # pragma: no cover - keeps management imports resilient.
    tenant_schema_context = None


PUBLIC_SCHEMA_NAME = "public"
RESERVED_SCHEMA_NAMES = {
    PUBLIC_SCHEMA_NAME,
    "information_schema",
    "pg_catalog",
    "pg_toast",
}
SCHEMA_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def normalize_schema_name(value):
    schema_name = slugify(str(value or "").strip()).replace("-", "_").lower()
    schema_name = re.sub(r"_+", "_", schema_name).strip("_")

    if not schema_name:
        raise ValueError("Schema name is required.")
    if schema_name[0].isdigit():
        schema_name = f"t_{schema_name}"

    schema_name = schema_name[:63].rstrip("_")
    if schema_name in RESERVED_SCHEMA_NAMES:
        raise ValueError(f"'{schema_name}' is a reserved schema name.")
    if not SCHEMA_NAME_PATTERN.match(schema_name):
        raise ValueError(
            "Schema name must contain only lowercase letters, numbers, and underscores."
        )
    return schema_name


def using_postgres():
    return connection.vendor == "postgresql"


def get_current_schema():
    return getattr(connection, "schema_name", PUBLIC_SCHEMA_NAME)


def reset_schema():
    if hasattr(connection, "set_schema_to_public"):
        connection.set_schema_to_public()


def activate_schema(schema_name):
    schema_name = normalize_schema_name(schema_name)
    if hasattr(connection, "set_schema"):
        connection.set_schema(schema_name)
    return schema_name


@contextmanager
def schema_context(schema_name):
    schema_name = normalize_schema_name(schema_name)
    if tenant_schema_context is not None:
        with tenant_schema_context(schema_name):
            yield
        return

    previous_schema = get_current_schema()
    activate_schema(schema_name)
    try:
        yield
    finally:
        if previous_schema == PUBLIC_SCHEMA_NAME:
            reset_schema()
        else:
            activate_schema(previous_schema)


def create_schema(schema_name):
    schema_name = normalize_schema_name(schema_name)
    if using_postgres():
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
    return schema_name


def migrate_tenant_schema(schema_name):
    # django-tenants owns schema migrations via migrate_schemas.
    # This wrapper remains for older imports during the SaaS transition.
    create_schema(schema_name)


def provision_tenant_schema(tenant):
    if hasattr(tenant, "create_schema"):
        tenant.create_schema(check_if_exists=True, sync_schema=True)
        return True

    create_schema(tenant.schema_name)
    if hasattr(tenant, "mark_schema_ready"):
        tenant.mark_schema_ready()
    return True
