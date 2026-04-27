# Generated for SaaS tenant/subscription support.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accesscontrol", "0001_initial"),
        ("user", "0003_businessprofile_color_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                ("code", models.SlugField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "billing_cycle",
                    models.CharField(
                        choices=[
                            ("monthly", "Monthly"),
                            ("yearly", "Yearly"),
                            ("lifetime", "Lifetime"),
                        ],
                        default="monthly",
                        max_length=20,
                    ),
                ),
                (
                    "max_users",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="0 means unlimited users.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "subscription_plan",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="Tenant",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                ("schema_name", models.SlugField(max_length=63, unique=True)),
                ("contact_name", models.CharField(blank=True, max_length=150)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("contact_phone", models.CharField(blank=True, max_length=30)),
                (
                    "subscription_status",
                    models.CharField(
                        choices=[
                            ("trialing", "Trialing"),
                            ("active", "Active"),
                            ("past_due", "Past Due"),
                            ("suspended", "Suspended"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="trialing",
                        max_length=20,
                    ),
                ),
                ("subscription_start_date", models.DateField(blank=True, null=True)),
                ("subscription_end_date", models.DateField(blank=True, null=True)),
                (
                    "schema_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("ready", "Ready"),
                            ("skipped", "Skipped"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("schema_error", models.TextField(blank=True)),
                ("provisioned_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_tenants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "subscription_plan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tenants",
                        to="user.subscriptionplan",
                    ),
                ),
            ],
            options={
                "db_table": "tenant",
                "ordering": ("name",),
            },
        ),
        migrations.AddField(
            model_name="tenant",
            name="enabled_modules",
            field=models.ManyToManyField(
                blank=True,
                related_name="tenants",
                to="accesscontrol.permissionmodule",
            ),
        ),
        migrations.AddField(
            model_name="usermodel",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                help_text="Tenant/customer account this user belongs to. Empty means platform user.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="users",
                to="user.tenant",
            ),
        ),
    ]
