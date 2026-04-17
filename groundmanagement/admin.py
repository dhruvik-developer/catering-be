from django.contrib import admin

from .models import (
    EventGroundRequirement,
    GroundCategory,
    GroundChecklistTemplate,
    GroundChecklistTemplateItem,
    GroundItem,
)


admin.site.register(GroundCategory)
admin.site.register(GroundItem)
admin.site.register(GroundChecklistTemplate)
admin.site.register(GroundChecklistTemplateItem)
admin.site.register(EventGroundRequirement)
