from django.contrib import admin
from .models import IngridientsCategory, IngridientsItem


@admin.register(IngridientsCategory)
class IngridientsCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_common"]
    search_fields = ["name"]


@admin.register(IngridientsItem)
class IngridientsItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category"]
    list_filter = ["category"]
    search_fields = ["name"]

