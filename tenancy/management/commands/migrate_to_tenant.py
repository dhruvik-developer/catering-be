from django.core.management.base import BaseCommand
from django.db import connection
from tenancy.models import Client, Domain


class Command(BaseCommand):
    help = "Migrates all data from public schema to a default tenant schema."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-name", type=str, default="Default Tenant")
        parser.add_argument("--schema-name", type=str, default="default")
        parser.add_argument("--domain", type=str, default="client1.localhost")

    def handle(self, *args, **options):
        tenant_name = options["tenant_name"]
        schema_name = options["schema_name"]
        domain_name = options["domain"]

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

            for table in tables:
                self.stdout.write(f"Copying table {table} to {schema_name}...")
                try:
                    # Clear existing data in tenant table if any (optional)
                    cursor.execute(f'TRUNCATE TABLE "{schema_name}"."{table}" CASCADE')
                    # Copy data
                    cursor.execute(f'INSERT INTO "{schema_name}"."{table}" SELECT * FROM "public"."{table}"')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to copy {table}: {e}"))

        self.stdout.write(self.style.SUCCESS("Migration completed successfully."))
