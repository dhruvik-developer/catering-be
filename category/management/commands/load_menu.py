import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import schema_context

from category.models import Category
from item.models import Item
from tenancy.models import Client
from tenancy.utils import normalize_schema_name


DEFAULT_BRANCH_PROFILE_ID = 1
DEFAULT_BASE_COST = 0
DEFAULT_SELECTION_RATE = 0


class Command(BaseCommand):
    help = (
        "Load the catering menu (categories, subcategories, items) from menu.json "
        "into a tenant schema. Idempotent: existing rows are reused via get_or_create."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            help="Tenant schema to load the menu into (e.g. bansuricatering).",
        )
        parser.add_argument(
            "--menu-file",
            default=None,
            help="Path to menu.json (defaults to <BASE_DIR>/menu.json).",
        )
        parser.add_argument(
            "--branch-profile-id",
            type=int,
            default=DEFAULT_BRANCH_PROFILE_ID,
            help="BranchProfile ID to attach to all created categories/items.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and print the plan without writing any rows.",
        )

    def handle(self, *args, **options):
        schema_name = normalize_schema_name(options["schema"])
        branch_profile_id = options["branch_profile_id"]
        dry_run = options["dry_run"]

        menu_path = Path(options["menu_file"]) if options["menu_file"] else Path(settings.BASE_DIR) / "menu.json"
        if not menu_path.exists():
            raise CommandError(f"Menu file not found: {menu_path}")

        with schema_context("public"):
            if not Client.objects.filter(schema_name=schema_name).exists():
                raise CommandError(
                    f"Tenant schema '{schema_name}' is not registered in tenant_client."
                )

        with menu_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        menu = payload.get("menu")
        if not isinstance(menu, dict):
            raise CommandError("menu.json must contain a top-level 'menu' object.")

        self._stats = {"categories_created": 0, "items_created": 0, "categories_reused": 0, "items_reused": 0}

        with schema_context(schema_name):
            if dry_run:
                self._walk_dry(menu, parent=None, depth=0)
                self.stdout.write(self.style.WARNING("Dry run only. No rows written."))
                return

            with transaction.atomic():
                for position, (name, content) in enumerate(menu.items(), start=1):
                    self._insert_node(name, content, parent=None, position=position, branch_profile_id=branch_profile_id)

        self.stdout.write(
            self.style.SUCCESS(
                "Menu loaded into '{schema}'. "
                "Categories: +{cc} (reused {cr}). Items: +{ic} (reused {ir}).".format(
                    schema=schema_name,
                    cc=self._stats["categories_created"],
                    cr=self._stats["categories_reused"],
                    ic=self._stats["items_created"],
                    ir=self._stats["items_reused"],
                )
            )
        )

    def _insert_node(self, name, content, parent, position, branch_profile_id):
        category, created = Category.objects.get_or_create(
            name=name,
            parent=parent,
            defaults={
                "branch_profile_id": branch_profile_id,
                "positions": position,
            },
        )
        if created:
            self._stats["categories_created"] += 1
        else:
            self._stats["categories_reused"] += 1
            if category.positions != position or category.branch_profile_id != branch_profile_id:
                category.positions = position
                category.branch_profile_id = branch_profile_id
                category.save(update_fields=["positions", "branch_profile_id"])

        if isinstance(content, list):
            for item_name in content:
                _, item_created = Item.objects.get_or_create(
                    category=category,
                    name=item_name,
                    defaults={
                        "branch_profile_id": branch_profile_id,
                        "base_cost": DEFAULT_BASE_COST,
                        "selection_rate": DEFAULT_SELECTION_RATE,
                    },
                )
                if item_created:
                    self._stats["items_created"] += 1
                else:
                    self._stats["items_reused"] += 1
        elif isinstance(content, dict):
            for sub_position, (sub_name, sub_content) in enumerate(content.items(), start=1):
                self._insert_node(
                    sub_name,
                    sub_content,
                    parent=category,
                    position=sub_position,
                    branch_profile_id=branch_profile_id,
                )
        else:
            raise CommandError(
                f"Unsupported value type under '{name}': {type(content).__name__}"
            )

    def _walk_dry(self, node, parent, depth):
        indent = "  " * depth
        for position, (name, content) in enumerate(node.items(), start=1):
            self.stdout.write(f"{indent}[cat pos={position}] {name} (parent={parent})")
            if isinstance(content, list):
                for item_name in content:
                    self.stdout.write(f"{indent}  - item: {item_name}")
            elif isinstance(content, dict):
                self._walk_dry(content, parent=name, depth=depth + 1)
