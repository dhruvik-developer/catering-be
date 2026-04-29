from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import schema_context

from tenancy.models import Client, Domain
from tenancy.utils import build_tenant_domain, normalize_domain, normalize_schema_name


class Command(BaseCommand):
    help = "Create the public tenant/domain and an optional default tenant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--public-domain",
            default="admin.localhost",
            help="Domain routed to the public schema, e.g. admin.trayza.in.",
        )
        parser.add_argument(
            "--default-schema",
            help="Optional default tenant schema to create from the existing company.",
        )
        parser.add_argument(
            "--default-domain",
            help="Optional default tenant domain. Defaults to <schema>.<SAAS_ROOT_DOMAIN>.",
        )
        parser.add_argument(
            "--default-name",
            default="Default Tenant",
            help="Display name for the default tenant.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("django-tenants SaaS setup requires PostgreSQL.")

        public_domain = normalize_domain(options["public_domain"])

        with schema_context("public"):
            public_client, _ = Client.objects.get_or_create(
                schema_name="public",
                defaults={
                    "name": "Platform Admin",
                    "subscription_status": Client.STATUS_ACTIVE,
                },
            )
            Domain.objects.update_or_create(
                domain=public_domain,
                defaults={"tenant": public_client, "is_primary": True},
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Public schema is mapped to domain '{public_domain}'."
                )
            )

            default_schema = options.get("default_schema")
            if not default_schema:
                return

            default_schema = normalize_schema_name(default_schema)
            default_domain = normalize_domain(
                options.get("default_domain") or build_tenant_domain(default_schema)
            )
            default_client, created = Client.objects.get_or_create(
                schema_name=default_schema,
                defaults={
                    "name": options["default_name"],
                    "subscription_status": Client.STATUS_ACTIVE,
                },
            )
            if not created:
                default_client.name = options["default_name"]
                default_client.subscription_status = Client.STATUS_ACTIVE
                default_client.save()

            Domain.objects.update_or_create(
                domain=default_domain,
                defaults={"tenant": default_client, "is_primary": True},
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Default tenant '{default_schema}' is mapped to '{default_domain}'."
                )
            )
