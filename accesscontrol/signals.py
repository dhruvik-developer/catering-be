from django.db.utils import OperationalError, ProgrammingError
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from accesscontrol.services import sync_permission_catalog


@receiver(post_migrate)
def seed_access_permissions(sender, **kwargs):
    try:
        sync_permission_catalog()
    except (OperationalError, ProgrammingError):
        return
