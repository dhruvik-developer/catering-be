from django.db.models.signals import post_save
from django.dispatch import receiver

from eventbooking.models import EventSession

from .models import (
    EventGroundRequirement,
    GroundChecklistTemplate,
)


@receiver(post_save, sender=EventSession)
def auto_create_ground_requirements(instance, created, **kwargs):
    if not created:
        return

    default_template = (
        GroundChecklistTemplate.objects.filter(
            branch_profile=instance.booking.branch_profile,
            is_active=True,
            is_default=True,
        )
        .prefetch_related("template_items__ground_item")
        .first()
    )
    if not default_template:
        return

    event_booking = instance.booking
    existing_item_ids = set(
        EventGroundRequirement.objects.filter(
            event_booking=event_booking,
            event_session=instance,
        ).values_list("ground_item_id", flat=True)
    )

    requirements_to_create = []
    for template_item in default_template.template_items.all():
        if template_item.ground_item_id in existing_item_ids:
            continue
        requirements_to_create.append(
            EventGroundRequirement(
                event_booking=event_booking,
                event_session=instance,
                ground_item=template_item.ground_item,
                required_quantity=template_item.required_quantity,
                arranged_quantity=0,
                is_required=template_item.is_required,
                notes=f"Auto-created from template: {default_template.name}",
            )
        )

    if requirements_to_create:
        EventGroundRequirement.objects.bulk_create(requirements_to_create)
