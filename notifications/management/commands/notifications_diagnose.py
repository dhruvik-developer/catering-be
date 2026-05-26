"""Diagnose the notification pipeline for a tenant.

Run:
    python manage.py notifications_diagnose --tenant <schema_name> [--branch <id>] [--send-test]

What it shows:
  - Which users would receive admin alerts (`iter_admin_recipients`).
  - Each admin's WS group name + active FCM device token count.
  - Optional: dispatch a real test notification so you can verify it
    arrives in the web bell / mobile app end-to-end.

Use this when "I accepted on mobile but nothing showed on the web" — if
the recipient list here is empty, that's the bug; if it's populated and
the test notification still doesn't arrive, the issue is on the
transport (Daphne / Redis / WS auth) and the row in
`notifications_notification` should confirm DB write succeeded.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import schema_context

from notifications.consumers import group_name_for
from notifications.models import DeviceToken, Notification
from notifications.services import NotificationService, iter_admin_recipients


class Command(BaseCommand):
    help = "Inspect admin notification recipients for a tenant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            help="Tenant schema name (e.g. 'pruthvi').",
        )
        parser.add_argument(
            "--branch",
            type=int,
            default=None,
            help="Optional branch_profile_id to scope branch_admin matches.",
        )
        parser.add_argument(
            "--send-test",
            action="store_true",
            help="Create a real Notification row + WS push + FCM send.",
        )

    def handle(self, *args, **options):
        schema = options["tenant"]
        branch_id = options["branch"]
        send_test = options["send_test"]

        # django-tenants will refuse to find tables if the schema is wrong, so
        # validate up front rather than crash mid-loop.
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                [schema],
            )
            if cur.fetchone() is None:
                raise CommandError(f"Tenant schema '{schema}' does not exist.")

        with schema_context(schema):
            recipients = list(iter_admin_recipients(branch_id))

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nAdmins resolved for tenant '{schema}' "
                f"(branch_profile_id={branch_id}):"
            ))
            if not recipients:
                self.stdout.write(self.style.ERROR(
                    "  (none)  ← this is why no alerts arrive."
                ))
                self.stdout.write(
                    "  Fix: ensure at least one user has is_superuser=True OR "
                    "branch_role='main_admin' OR is_staff=True."
                )
            else:
                for user in recipients:
                    token_count = DeviceToken.objects.filter(
                        user=user, is_active=True
                    ).count()
                    self.stdout.write(
                        f"  • id={user.id}  username={user.username!r}  "
                        f"branch_role={user.branch_role!r}  "
                        f"is_staff={user.is_staff}  is_superuser={user.is_superuser}  "
                        f"branch_profile_id={user.branch_profile_id}  "
                        f"active_fcm_tokens={token_count}"
                    )
                    self.stdout.write(
                        f"      ws_group={group_name_for(schema, user.id)!r}"
                    )

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nNotification rows in '{schema}':"
            ))
            total = Notification.objects.count()
            unread = Notification.objects.filter(is_read=False).count()
            self.stdout.write(f"  total={total}  unread={unread}")

            if send_test and recipients:
                self.stdout.write(self.style.MIGRATE_HEADING(
                    "\nSending test notification to each recipient…"
                ))
                for user in recipients:
                    notif = NotificationService.notify_user(
                        user,
                        notification_type=Notification.TYPE_GENERIC,
                        title="Diagnostic test alert",
                        message=(
                            "If you see this, the notification pipeline "
                            "is working for your account."
                        ),
                        data={"route": "/dashboard", "diagnostic": True},
                    )
                    self.stdout.write(
                        f"  • user={user.username!r}: "
                        f"{'created notif id=' + str(notif.id) if notif else 'SKIPPED'}"
                    )
                self.stdout.write(self.style.SUCCESS(
                    "Done. Refresh the web/mobile app — the alert should appear."
                ))
