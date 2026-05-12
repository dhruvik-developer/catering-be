from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_tenants.utils import schema_context, tenant_context

from tenancy.models import Client
from tenancy.utils import PUBLIC_SCHEMA_NAME, normalize_schema_name
from user.branching import ensure_main_branch_profile


class Command(BaseCommand):
    help = "Assign legacy tenant rows with no branch_profile to the main branch."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Tenant schema to repair.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show rows that would be updated without saving changes.",
        )

    def handle(self, *args, **options):
        schema_name = normalize_schema_name(options["schema"])
        if schema_name == PUBLIC_SCHEMA_NAME:
            raise CommandError("Branch repair must target a tenant schema.")

        with schema_context(PUBLIC_SCHEMA_NAME):
            try:
                tenant = Client.objects.get(schema_name=schema_name)
            except Client.DoesNotExist as exc:
                raise CommandError(
                    f"Tenant schema '{schema_name}' was not found."
                ) from exc

        dry_run = options["dry_run"]
        repaired = []

        with tenant_context(tenant):
            table_names = set(connection.introspection.table_names())
            branch = ensure_main_branch_profile(tenant=tenant)

            with transaction.atomic():
                for model in self._get_branch_models(table_names):
                    field = model._meta.get_field("branch_profile")
                    queryset = model._default_manager.filter(
                        **{f"{field.name}__isnull": True}
                    )
                    count = queryset.count()
                    if not count:
                        continue

                    if not dry_run:
                        queryset.update(**{field.attname: branch.pk})
                    repaired.append((model._meta.label, count))

                if dry_run:
                    transaction.set_rollback(True)

        if not repaired:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No missing branch_profile values found in '{schema_name}'."
                )
            )
            return

        action = "Would assign" if dry_run else "Assigned"
        for label, count in repaired:
            self.stdout.write(f"{label}: {count}")

        self.stdout.write(
            self.style.SUCCESS(
                f"{action} main branch to {sum(count for _, count in repaired)} "
                f"row(s) across {len(repaired)} model(s) in '{schema_name}'."
            )
        )

    def _get_branch_models(self, table_names):
        models = []
        for model in apps.get_models():
            if model._meta.proxy or not model._meta.managed:
                continue
            if model._meta.db_table not in table_names:
                continue
            try:
                field = model._meta.get_field("branch_profile")
            except Exception:
                continue
            if getattr(field.remote_field, "model", None)._meta.label == "user.BranchProfile":
                models.append(model)
        return sorted(models, key=lambda model: model._meta.label_lower)
