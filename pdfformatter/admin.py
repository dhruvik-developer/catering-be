from django.contrib import admin

from .models import PdfFormatter


@admin.register(PdfFormatter)
class PdfFormatterAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "is_default",
        "is_active",
        "created_by",
        "updated_at",
    )
    list_filter = ("is_default", "is_active")
    search_fields = ("name", "code", "description")
    readonly_fields = ("created_at", "updated_at")
