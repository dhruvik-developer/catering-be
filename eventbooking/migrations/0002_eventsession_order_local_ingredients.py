from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eventbooking", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventsession",
            name="order_local_ingredients",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
