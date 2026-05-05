from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import schema_context, tenant_context

from tenancy.models import Client


TOKEN_BLACKLIST_APP = "token_blacklist"
TOKEN_BLACKLIST_INITIAL_MIGRATION = "0001_initial"
TOKEN_BLACKLIST_TABLES = (
    "token_blacklist_outstandingtoken",
    "token_blacklist_blacklistedtoken",
)


class Command(BaseCommand):
    help = (
        "Repair tenant JWT blacklist tables when token_blacklist was previously "
        "marked as migrated before it was enabled as a tenant app."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            dest="schema_name",
            help="Repair only one tenant schema.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show schemas that need repair without changing migrations.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        schema_name = options.get("schema_name")

        tenants = self._get_tenants(schema_name)
        if not tenants:
            self.stdout.write("No tenant schemas found.")
            return

        repaired = []
        checked = 0

        for tenant in tenants:
            checked += 1
            status = self._get_schema_status(tenant)
            missing_tables = [
                table
                for table in TOKEN_BLACKLIST_TABLES
                if table not in status["existing_tables"]
            ]

            if not missing_tables:
                self.stdout.write(f"{tenant.schema_name}: token blacklist tables OK.")
                continue

            if status["existing_tables"]:
                raise CommandError(
                    f"{tenant.schema_name}: partial token blacklist schema found. "
                    f"Existing: {sorted(status['existing_tables'])}; "
                    f"missing: {missing_tables}. Please repair manually to avoid data loss."
                )

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"{tenant.schema_name}: needs repair; missing {missing_tables}."
                    )
                )
                continue

            self.stdout.write(f"{tenant.schema_name}: repairing token blacklist tables...")
            self._repair_schema(tenant.schema_name, status["has_migration_record"])
            repaired.append(tenant.schema_name)

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete; no changes saved."))
            return

        if repaired:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Repaired {len(repaired)} of {checked} tenant schema(s): "
                    f"{', '.join(repaired)}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"No tenant token blacklist repairs needed ({checked} checked).")
            )

    def _get_tenants(self, schema_name):
        with schema_context("public"):
            tenants = Client.objects.exclude(schema_name="public").only(
                "schema_name",
                "name",
            )
            if schema_name:
                tenants = tenants.filter(schema_name=schema_name)
                if not tenants.exists():
                    raise CommandError(f"Tenant schema '{schema_name}' was not found.")
            return list(tenants.order_by("schema_name"))

    def _get_schema_status(self, tenant):
        with tenant_context(tenant):
            existing_tables = set()
            with connection.cursor() as cursor:
                for table in TOKEN_BLACKLIST_TABLES:
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE n.nspname = current_schema()
                              AND c.relkind IN ('r', 'p')
                              AND c.relname = %s
                        )
                        """,
                        [table],
                    )
                    if cursor.fetchone()[0]:
                        existing_tables.add(table)

                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM django_migrations
                        WHERE app = %s AND name = %s
                    )
                    """,
                    [TOKEN_BLACKLIST_APP, TOKEN_BLACKLIST_INITIAL_MIGRATION],
                )
                has_migration_record = cursor.fetchone()[0]

            return {
                "existing_tables": existing_tables,
                "has_migration_record": has_migration_record,
            }

    def _repair_schema(self, schema_name, has_migration_record):
        connection.set_schema_to_public()

        migrate_options = {
            "tenant": True,
            "schema_name": schema_name,
            "interactive": False,
            "verbosity": 1,
        }

        if has_migration_record:
            call_command(
                "migrate_schemas",
                TOKEN_BLACKLIST_APP,
                "zero",
                fake=True,
                **migrate_options,
            )

        call_command(
            "migrate_schemas",
            TOKEN_BLACKLIST_APP,
            **migrate_options,
        )
        connection.set_schema_to_public()
