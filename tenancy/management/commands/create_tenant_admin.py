from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from tenancy.models import Client
from tenancy.services import create_tenant_admin_user


class Command(BaseCommand):
    help = "Create a tenant admin user inside an existing tenant schema."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Tenant schema name.")
        parser.add_argument("--username", required=True, help="Admin username.")
        parser.add_argument("--password", required=True, help="Admin password.")
        parser.add_argument("--email", default="", help="Admin email.")
        parser.add_argument("--first-name", default="", help="Admin first name.")
        parser.add_argument("--last-name", default="", help="Admin last name.")
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Also mark the tenant admin as a Django superuser.",
        )

    def handle(self, *args, **options):
        schema_name = options["schema"]
        with schema_context("public"):
            try:
                tenant = Client.objects.get(schema_name=schema_name)
            except Client.DoesNotExist as exc:
                raise CommandError(f"Tenant schema '{schema_name}' does not exist.") from exc

        admin_data = {
            "username": options["username"],
            "password": options["password"],
            "email": options["email"],
            "first_name": options["first_name"],
            "last_name": options["last_name"],
            "is_superuser": options["superuser"],
        }

        try:
            create_tenant_admin_user(tenant, admin_data)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Tenant admin '{options['username']}' created in schema '{schema_name}'."
            )
        )
