from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenancy.db_sequences import reset_schema_sequences
from tenancy.utils import PUBLIC_SCHEMA_NAME, normalize_schema_name


class Command(BaseCommand):
    help = "Reset PostgreSQL sequences for one schema to match existing row ids."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Schema to repair.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Sequence repair requires PostgreSQL.")

        raw_schema_name = options["schema"]
        if raw_schema_name == PUBLIC_SCHEMA_NAME:
            schema_name = PUBLIC_SCHEMA_NAME
        else:
            schema_name = normalize_schema_name(raw_schema_name)

        with connection.cursor() as cursor:
            reset_sequences = reset_schema_sequences(cursor, schema_name)

        if not reset_sequences:
            self.stdout.write(
                self.style.WARNING(
                    f"No sequence-backed columns found in schema '{schema_name}'."
                )
            )
            return

        for table_name, column_name, value in reset_sequences:
            self.stdout.write(f"{table_name}.{column_name} -> {value}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Reset {len(reset_sequences)} sequence(s) in schema '{schema_name}'."
            )
        )
