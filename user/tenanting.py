import re
import threading
from contextlib import contextmanager

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.utils.text import slugify


PUBLIC_SCHEMA_NAME = "public"
RESERVED_SCHEMA_NAMES = {
    PUBLIC_SCHEMA_NAME,
    "information_schema",
    "pg_catalog",
    "pg_toast",
}
SCHEMA_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
_state = threading.local()


def using_postgres():
    return connection.vendor == "postgresql"


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


def get_current_schema():
    return getattr(_state, "schema_name", PUBLIC_SCHEMA_NAME)


def _quote_schema_name(schema_name):
    return connection.ops.quote_name(normalize_schema_name(schema_name))


def reset_schema():
    _state.schema_name = PUBLIC_SCHEMA_NAME
    if not using_postgres():
        return

    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")


def activate_schema(schema_name):
    schema_name = normalize_schema_name(schema_name)
    _state.schema_name = schema_name

    if not using_postgres():
        return schema_name

    with connection.cursor() as cursor:
        cursor.execute(
            f"SET search_path TO {_quote_schema_name(schema_name)}, public"
        )
    return schema_name


@contextmanager
def schema_context(schema_name):
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
    if not using_postgres():
        return schema_name

    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote_schema_name(schema_name)}")
    return schema_name


def mark_shared_migrations_as_applied():
    shared_app_labels = set(
        getattr(
            settings,
            "SAAS_SHARED_APPS",
            (
                "admin",
                "auth",
                "contenttypes",
                "sessions",
                "authtoken",
                "accesscontrol",
                "user",
            ),
        )
    )

    recorder = MigrationRecorder(connection)
    recorder.ensure_schema()
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    applied_migrations = recorder.applied_migrations()

    for app_label, migration_name in loader.disk_migrations:
        if app_label not in shared_app_labels:
            continue
        if (app_label, migration_name) in applied_migrations:
            continue
        recorder.record_applied(app_label, migration_name)


def _iter_tenant_only_models_from_shared_apps():
    model_labels = getattr(
        settings,
        "SAAS_TENANT_SHARED_APP_MODELS",
        ("user.Note", "user.BusinessProfile"),
    )

    for model_label in model_labels:
        app_label, model_name = model_label.split(".", 1)
        yield apps.get_model(app_label, model_name)


def _schema_table_exists(schema_name, table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s
            )
            """,
            [schema_name, table_name],
        )
        return cursor.fetchone()[0]


def create_tenant_only_model_tables(schema_name):
    if not using_postgres():
        return

    schema_name = normalize_schema_name(schema_name)
    with connection.schema_editor() as schema_editor:
        for model in _iter_tenant_only_models_from_shared_apps():
            if _schema_table_exists(schema_name, model._meta.db_table):
                continue
            schema_editor.create_model(model)


def migrate_tenant_schema(schema_name):
    if not using_postgres():
        return

    with schema_context(schema_name):
        mark_shared_migrations_as_applied()
        call_command(
            "migrate",
            database="default",
            interactive=False,
            verbosity=0,
        )
        activate_schema(schema_name)
        create_tenant_only_model_tables(schema_name)


def provision_tenant_schema(tenant):
    if not using_postgres():
        tenant.mark_schema_skipped(
            "Schema provisioning requires PostgreSQL. SQLite development mode uses the public schema."
        )
        return False

    try:
        schema_name = create_schema(tenant.schema_name)
        if tenant.schema_name != schema_name:
            tenant.schema_name = schema_name
            tenant.save(update_fields=["schema_name", "updated_at"])
        migrate_tenant_schema(schema_name)
    except Exception as exc:
        reset_schema()
        tenant.mark_schema_failed(exc)
        raise

    reset_schema()
    tenant.mark_schema_ready()
    return True
