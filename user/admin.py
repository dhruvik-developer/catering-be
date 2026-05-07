from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accesscontrol.models import UserPermissionAssignment

from .models import BranchProfile, UserModel


class UserPermissionAssignmentInline(admin.TabularInline):
    model = UserPermissionAssignment
    extra = 0
    autocomplete_fields = ("permission",)
    fields = ("permission", "is_allowed", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(UserModel)
class CustomUserAdmin(UserAdmin):
    model = UserModel
    fieldsets = UserAdmin.fieldsets + (
        ("Branch", {"fields": ("branch_profile",)}),
    )
    list_display = (
        "username",
        "email",
        "branch_profile",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    list_filter = ("branch_profile", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "branch_profile__name", "branch_profile__city")
    autocomplete_fields = ("branch_profile",)
    ordering = ("username",)
    inlines = (UserPermissionAssignmentInline,)


@admin.register(BranchProfile)
class BranchProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "branch_code",
        "city",
        "state",
        "manager",
        "is_main",
        "is_active",
    )
    list_filter = ("is_main", "is_active", "city", "state")
    search_fields = ("name", "branch_code", "city", "state", "manager__username")
    autocomplete_fields = ("manager", "created_by")
