import json

from django.core.management.base import BaseCommand

from accesscontrol.catalog import build_permission_catalog
from accesscontrol.services import sync_permission_catalog


class Command(BaseCommand):
    help = "Discover permissions from project views and sync them into access control tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--print-catalog",
            action="store_true",
            help="Print discovered permission catalog JSON before syncing.",
        )

    def handle(self, *args, **options):
        catalog = build_permission_catalog()

        if options["print_catalog"]:
            self.stdout.write(json.dumps(catalog, indent=2))

        result = sync_permission_catalog(catalog=catalog)

        self.stdout.write(
            self.style.SUCCESS(
                "Permission sync complete. "
                f"Modules active: {result['active_modules']}, "
                f"Permissions active: {result['active_permissions']}."
            )
        )
