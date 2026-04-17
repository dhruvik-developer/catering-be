from django.contrib import admin
from .models import Item, RecipeIngredient


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1
    autocomplete_fields = ["ingredient"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "base_cost", "selection_rate"]
    list_filter = ["category"]
    search_fields = ["name"]
    inlines = [RecipeIngredientInline]


@admin.register(RecipeIngredient)
class RecipeIngredientAdmin(admin.ModelAdmin):
    list_display = ["item", "ingredient", "quantity", "unit", "person_count"]
    list_filter = ["item", "ingredient__category"]
    autocomplete_fields = ["item", "ingredient"]

