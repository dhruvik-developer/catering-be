from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Lead",
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
                ("full_name", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=255)),
                ("phone", models.CharField(blank=True, default="", max_length=20)),
                ("company", models.CharField(blank=True, default="", max_length=120)),
                ("message", models.TextField(max_length=2000)),
                (
                    "source",
                    models.CharField(blank=True, default="website", max_length=60),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("converted", "Converted"),
                            ("closed", "Closed"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(
                fields=["status"], name="leads_lead_status_e23abe_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(
                fields=["created_at"], name="leads_lead_created_302c6d_idx"
            ),
        ),
    ]
