from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accesscontrol.models import UserPermissionAssignment

from .models import UserModel


class UserPermissionAssignmentInline(admin.TabularInline):
    model = UserPermissionAssignment
    extra = 0
    autocomplete_fields = ("permission",)
    fields = ("permission", "is_allowed", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(UserModel)
class CustomUserAdmin(UserAdmin):
    model = UserModel
    list_display = (
        "username",
        "email",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email")
    ordering = ("username",)
    inlines = (UserPermissionAssignmentInline,)
