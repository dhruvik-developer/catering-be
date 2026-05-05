from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from tenancy.models import Client


class Command(BaseCommand):
    help = (
        "Roll subscription statuses forward based on dates. "
        "Trialing -> Active once the trial window ends. "
        "Active/Trialing -> Past Due once the subscription end date passes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today = timezone.localdate()

        with schema_context("public"):
            clients = (
                Client.objects.exclude(schema_name="public")
                .select_related("subscription_plan")
            )

            transitions = []
            for client in clients:
                new_status = self._next_status(client, today)
                if new_status and new_status != client.subscription_status:
                    transitions.append((client, new_status))

            if not transitions:
                self.stdout.write("No subscription status changes needed.")
                return

            for client, new_status in transitions:
                self.stdout.write(
                    f"  {client.schema_name}: {client.subscription_status} -> {new_status}"
                )

            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run — no changes saved."))
                return

            with transaction.atomic():
                for client, new_status in transitions:
                    client.subscription_status = new_status
                    client.save(update_fields=["subscription_status", "updated_at"])

            self.stdout.write(
                self.style.SUCCESS(f"Updated {len(transitions)} tenant(s).")
            )

    @staticmethod
    def _next_status(client, today):
        # Skip tenants without a plan or start date — nothing to roll forward.
        if not client.subscription_plan_id or not client.subscription_start_date:
            return None

        status = client.subscription_status
        end_date = client.subscription_end_date

        # Past-due wins: if the subscription has already expired, mark it.
        # Lifetime plans (no end_date) are never past-due here.
        if end_date and today > end_date and status in {
            Client.STATUS_TRIALING,
            Client.STATUS_ACTIVE,
        }:
            return Client.STATUS_PAST_DUE

        # Trial -> Active once the trial window has elapsed.
        if status == Client.STATUS_TRIALING:
            trial_days = client.subscription_plan.trial_days or 0
            trial_end = client.subscription_start_date + timedelta(days=trial_days)
            if today >= trial_end:
                return Client.STATUS_ACTIVE

        return None
