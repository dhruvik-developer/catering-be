from django.contrib import admin

from .models import Vendor, VendorCategory


class VendorCategoryInline(admin.TabularInline):
    model = VendorCategory
    extra = 1


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "mobile_no", "user_account", "is_active")
    search_fields = ("name", "mobile_no", "user_account__username")
    list_filter = ("is_active",)
    inlines = [VendorCategoryInline]

# Register your models here.
