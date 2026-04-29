from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from tenancy.models import Client, SubscriptionPlan


@receiver(m2m_changed, sender=SubscriptionPlan.included_modules.through)
def resync_clients_on_plan_modules_change(sender, instance, action, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if not isinstance(instance, SubscriptionPlan):
        return
    for client in Client.objects.filter(subscription_plan=instance):
        client.sync_modules_from_plan()
