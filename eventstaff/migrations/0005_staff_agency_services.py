from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eventstaff", "0004_staffrolepermissionassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="staff",
            name="agency_services",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of {service_name, rate} entries. Used when staff_type=Agency.",
                verbose_name="Agency Services",
            ),
        ),
    ]
