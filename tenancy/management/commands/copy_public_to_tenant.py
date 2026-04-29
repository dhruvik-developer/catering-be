from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_tenants.utils import schema_context

from tenancy.models import Client
from tenancy.utils import normalize_schema_name


EXCLUDED_TABLES = {
    "django_migrations",
    "tenant_client",
    "tenant_domain",
    "tenant_client_enabled_modules",
    "saas_subscription_plan",
}


class Command(BaseCommand):
    help = (
        "Copy existing single-tenant public data into one tenant schema. "
        "Rows are inserted with ON CONFLICT DO NOTHING and public data is not deleted."
    )

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Destination tenant schema.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print table copy plan without writing data.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Data copy requires PostgreSQL.")

        schema_name = normalize_schema_name(options["schema"])
        dry_run = options["dry_run"]

        with schema_context("public"):
            if not Client.objects.filter(schema_name=schema_name).exists():
                raise CommandError(
                    f"Tenant schema '{schema_name}' is not registered. "
                    "Run bootstrap_saas first."
                )

        table_names = self._get_copyable_tables(schema_name)
        if not table_names:
            self.stdout.write(self.style.WARNING("No copyable tables found."))
            return

        for table_name in table_names:
            self.stdout.write(f"{table_name}: public -> {schema_name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only. No rows copied."))
            return

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL session_replication_role = replica")
                for table_name in table_names:
                    quoted_table = connection.ops.quote_name(table_name)
                    quoted_schema = connection.ops.quote_name(schema_name)
                    cursor.execute(
                        f"""
                        INSERT INTO {quoted_schema}.{quoted_table}
                        SELECT * FROM public.{quoted_table}
                        ON CONFLICT DO NOTHING
                        """
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Copied public data into tenant schema '{schema_name}'."
            )
        )

    def _get_copyable_tables(self, schema_name):
        model_tables = {
            model._meta.db_table
            for model in apps.get_models()
            if not model._meta.proxy and model._meta.managed
        }

        table_names = []
        with connection.cursor() as cursor:
            for table_name in sorted(model_tables):
                if table_name in EXCLUDED_TABLES:
                    continue
                if self._table_exists(cursor, "public", table_name) and self._table_exists(
                    cursor,
                    schema_name,
                    table_name,
                ):
                    table_names.append(table_name)
        return table_names

    def _table_exists(self, cursor, schema_name, table_name):
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
