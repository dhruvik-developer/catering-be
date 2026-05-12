from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenancy.db_sequences import reset_schema_sequences
from tenancy.models import Client, Domain
from tenancy.utils import normalize_domain, normalize_schema_name


class Command(BaseCommand):
    help = "Migrates all data from public schema to a default tenant schema."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-name", type=str, default="Default Tenant")
        parser.add_argument("--schema-name", type=str, default="default")
        parser.add_argument("--domain", type=str, default="client1.localhost")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Tenant migration requires PostgreSQL.")

        tenant_name = options["tenant_name"]
        schema_name = normalize_schema_name(options["schema_name"])
        domain_name = normalize_domain(options["domain"])

        self.stdout.write(f"Migrating data to tenant: {tenant_name} ({schema_name})")

        # 1. Create Tenant if not exists
        tenant, created = Client.objects.get_or_create(
            schema_name=schema_name,
            defaults={"name": tenant_name}
        )
        
        if created:
            self.stdout.write(f"Created tenant {tenant_name}")
            Domain.objects.get_or_create(
                domain=domain_name,
                tenant=tenant,
                is_primary=True
            )
        
        # 2. Trigger schema creation and migration
        # django-tenants handles this when Client.save() is called or via migrate_schemas
        # but since we might already have data, we'll manually copy tables.
        
        with connection.cursor() as cursor:
            # Get all tables in public schema
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                AND table_name NOT LIKE 'tenant_%'
                AND table_name NOT LIKE 'django_%'
            """)
            tables = [row[0] for row in cursor.fetchall()]
            copied_tables = []
            quoted_schema = connection.ops.quote_name(schema_name)

            for table in tables:
                self.stdout.write(f"Copying table {table} to {schema_name}...")
                try:
                    quoted_table = connection.ops.quote_name(table)
                    # Clear existing data in tenant table if any (optional)
                    cursor.execute(
                        f"TRUNCATE TABLE {quoted_schema}.{quoted_table} CASCADE"
                    )
                    # Copy data
                    cursor.execute(
                        f"""
                        INSERT INTO {quoted_schema}.{quoted_table}
                        SELECT * FROM public.{quoted_table}
                        """
                    )
                    copied_tables.append(table)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to copy {table}: {e}"))

            reset_sequences = reset_schema_sequences(
                cursor,
                schema_name,
                copied_tables,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Migration completed successfully. "
                f"Reset {len(reset_sequences)} sequence(s)."
            )
        )
