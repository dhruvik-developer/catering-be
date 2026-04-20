from django.contrib import admin

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    StaffRolePermissionAssignment,
    UserPermissionAssignment,
)


@admin.register(PermissionModule)
class PermissionModuleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("sort_order", "name")


@admin.register(AccessPermission)
class AccessPermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "module", "action", "is_active")
    list_filter = ("module", "action", "is_active")
    search_fields = ("name", "code")
    ordering = ("module__sort_order", "sort_order", "name")


@admin.register(UserPermissionAssignment)
class UserPermissionAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "is_allowed", "updated_at")
    list_filter = ("is_allowed", "permission__module")
    search_fields = ("user__username", "permission__code")


@admin.register(StaffRolePermissionAssignment)
class StaffRolePermissionAssignmentAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "updated_at")
    list_filter = ("permission__module",)
    search_fields = ("role__name", "permission__code")
