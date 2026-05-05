from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0003_subscriptionplan_trial_days'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscriptionplan',
            name='billing_cycle',
            field=models.CharField(
                choices=[
                    ('monthly', 'Monthly'),
                    ('quarterly', 'Quarterly'),
                    ('yearly', 'Yearly'),
                    ('lifetime', 'Lifetime'),
                ],
                default='monthly',
                max_length=20,
            ),
        ),
    ]
