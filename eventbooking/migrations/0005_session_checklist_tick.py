# Hand-written migration: adds the per-session checklist persistence table.
# Each row records one tick state for a derived row in the checklist UI
# (menu item / ingredient / outsourced item / vendor / ground item) so the
# mobile app and web admin can show the previous state on reopen.
#
# Run with: `python manage.py migrate eventbooking`
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eventbooking", "0004_eventbooking_branch_profile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionChecklistTick",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("item_key", models.CharField(max_length=255)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("prepared", "Prepared"),
                            ("served", "Served"),
                            ("received", "Received"),
                            ("delivered", "Delivered"),
                            ("available", "Available"),
                        ],
                        max_length=20,
                    ),
                ),
                ("is_done", models.BooleanField(default=False)),
                ("ticked_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checklist_ticks",
                        to="eventbooking.eventsession",
                    ),
                ),
                (
                    "ticked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="session_checklist_ticks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("session", "item_key", "action"),
            },
        ),
        migrations.AddConstraint(
            model_name="sessionchecklisttick",
            constraint=models.UniqueConstraint(
                fields=("session", "item_key", "action"),
                name="uniq_session_checklist_tick",
            ),
        ),
    ]
