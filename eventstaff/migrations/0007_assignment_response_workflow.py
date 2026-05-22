# Hand-written migration: adds the staff response workflow.
#   - Three fields on EventStaffAssignment (response_status / decline_reason /
#     responded_at) so the booking detail can show whether the assigned staff
#     accepted, declined, or hasn't replied yet.
#   - A new EventStaffAssignmentResponse table that logs every accept / decline
#     action so admins can see the full reassignment history on one booking.
#
# Run with: `python manage.py migrate eventstaff`
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eventstaff', '0006_staff_branch_profile_staffrole_branch_profile_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='eventstaffassignment',
            name='response_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('accepted', 'Accepted'),
                    ('declined', 'Declined'),
                ],
                default='pending',
                max_length=12,
                verbose_name='Staff Response Status',
            ),
        ),
        migrations.AddField(
            model_name='eventstaffassignment',
            name='decline_reason',
            field=models.TextField(
                blank=True,
                default='',
                help_text="Required when response_status is 'declined'.",
                verbose_name='Decline Reason',
            ),
        ),
        migrations.AddField(
            model_name='eventstaffassignment',
            name='responded_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Timestamp of the latest accept/decline by the assigned staff.',
                verbose_name='Responded At',
            ),
        ),
        migrations.CreateModel(
            name='EventStaffAssignmentResponse',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('response', models.CharField(
                    choices=[('accepted', 'Accepted'), ('declined', 'Declined')],
                    max_length=12,
                    verbose_name='Response',
                )),
                ('reason', models.TextField(
                    blank=True,
                    default='',
                    help_text='Required for declines, optional for acceptances.',
                    verbose_name='Reason',
                )),
                ('responded_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Responded At')),
                ('assignment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='response_history',
                    to='eventstaff.eventstaffassignment',
                    verbose_name='Assignment',
                )),
                ('responded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='staff_assignment_responses',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Responded By',
                )),
            ],
            options={
                'verbose_name': 'Event Staff Assignment Response',
                'verbose_name_plural': 'Event Staff Assignment Responses',
                'ordering': ('-responded_at',),
            },
        ),
    ]
