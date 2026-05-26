# Hand-written migration: adds vendor-side accept/decline + driver capture
# tables. EventVendorAssignment mirrors EventStaffAssignment so the vendor
# portal in the mobile app can show the same Accept/Decline flow that staff
# already have. EventVendorAssignmentResponse is the append-only audit trail.
#
# Run with: `python manage.py migrate eventbooking`
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eventbooking", "0005_session_checklist_tick"),
        ("vendor", "0003_vendor_branch_profile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EventVendorAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "response_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("declined", "Declined"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("decline_reason", models.TextField(blank=True, default="")),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("declined_item_keys", models.JSONField(blank=True, default=list)),
                ("driver_name", models.CharField(blank=True, default="", max_length=120)),
                ("driver_phone", models.CharField(blank=True, default="", max_length=30)),
                ("driver_eta", models.DateTimeField(blank=True, null=True)),
                ("dispatched_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vendor_assignments",
                        to="eventbooking.eventsession",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="event_vendor_assignments",
                        to="vendor.vendor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Event Vendor Assignment",
                "verbose_name_plural": "Event Vendor Assignments",
                "ordering": ("session", "vendor"),
                "unique_together": {("session", "vendor")},
            },
        ),
        migrations.CreateModel(
            name="EventVendorAssignmentResponse",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("item_key", models.CharField(blank=True, default="", max_length=255)),
                (
                    "response",
                    models.CharField(
                        choices=[
                            ("accepted", "Accepted"),
                            ("declined", "Declined"),
                        ],
                        max_length=12,
                    ),
                ),
                ("reason", models.TextField(blank=True, default="")),
                (
                    "responded_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="response_history",
                        to="eventbooking.eventvendorassignment",
                    ),
                ),
                (
                    "responded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vendor_assignment_responses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Event Vendor Assignment Response",
                "verbose_name_plural": "Event Vendor Assignment Responses",
                "ordering": ("-responded_at",),
            },
        ),
    ]
