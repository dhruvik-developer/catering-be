import re

from django.conf import settings
from django.utils.text import slugify


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


def normalize_domain(value):
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = domain.split("/", 1)[0].split(":", 1)[0]
    return domain


def build_tenant_domain(schema_name):
    root_domain = getattr(settings, "SAAS_ROOT_DOMAIN", "localhost")
    return normalize_domain(f"{schema_name}.{root_domain}")


def is_public_schema(schema_name):
    return (schema_name or PUBLIC_SCHEMA_NAME) == PUBLIC_SCHEMA_NAME
