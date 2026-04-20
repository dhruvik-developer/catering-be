from django.conf import settings
from django.db import models


class PermissionModule(models.Model):
    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class AccessPermission(models.Model):
    module = models.ForeignKey(
        PermissionModule,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    code = models.CharField(max_length=150, unique=True)
    action = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("module__sort_order", "sort_order", "name")

    def __str__(self):
        return self.code


class UserPermissionAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="permission_assignments",
    )
    permission = models.ForeignKey(
        AccessPermission,
        on_delete=models.CASCADE,
        related_name="user_assignments",
    )
    is_allowed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "permission")
        ordering = ("user__username", "permission__code")

    def __str__(self):
        state = "allow" if self.is_allowed else "deny"
        return f"{self.user.username} -> {self.permission.code} ({state})"


class StaffRolePermissionAssignment(models.Model):
    role = models.ForeignKey(
        "eventstaff.StaffRole",
        on_delete=models.CASCADE,
        related_name="permission_assignments",
    )
    permission = models.ForeignKey(
        AccessPermission,
        on_delete=models.CASCADE,
        related_name="staff_role_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("role", "permission")
        ordering = ("role__name", "permission__code")

    def __str__(self):
        return f"{self.role.name} -> {self.permission.code}"
