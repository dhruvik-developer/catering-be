from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)
from user.models import Tenant


UserModel = get_user_model()


class UserCreationAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = UserModel.objects.create_superuser(
            username="admin-user",
            email="admin@example.com",
            password="admin1234",
        )
        self.manager = UserModel.objects.create_user(
            username="manager-user",
            email="manager@example.com",
            password="manager1234",
        )

        module, _ = PermissionModule.objects.get_or_create(
            code="users",
            defaults={"name": "Users"},
        )
        create_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="users.create",
            defaults={
                "action": "create",
                "name": "Create User",
            },
        )
        view_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="users.view",
            defaults={
                "action": "view",
                "name": "View User",
            },
        )

        UserPermissionAssignment.objects.create(
            user=self.manager,
            permission=create_permission,
            is_allowed=True,
        )
        UserPermissionAssignment.objects.create(
            user=self.manager,
            permission=view_permission,
            is_allowed=True,
        )

    def test_non_admin_cannot_create_user_even_with_create_permission(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/users/",
            {
                "username": "new-user",
                "email": "new@example.com",
                "password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            str(response.data["detail"]),
            "Only platform admin or tenant admin can create this resource.",
        )
        self.assertFalse(UserModel.objects.filter(username="new-user").exists())

    def test_admin_can_create_user(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/users/",
            {
                "username": "created-by-admin",
                "email": "created@example.com",
                "password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])
        self.assertTrue(UserModel.objects.filter(username="created-by-admin").exists())

    def test_non_admin_with_view_permission_can_still_list_users(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "User list fetched successfully.")


class TenantSaaSTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.platform_admin = UserModel.objects.create_superuser(
            username="platform-admin",
            email="platform@example.com",
            password="admin1234",
        )
        self.category_module, _ = PermissionModule.objects.get_or_create(
            code="categories",
            defaults={"name": "Categories"},
        )
        self.users_module, _ = PermissionModule.objects.get_or_create(
            code="users",
            defaults={"name": "Users"},
        )
        AccessPermission.objects.get_or_create(
            module=self.category_module,
            code="categories.view",
            defaults={"action": "view", "name": "View categories"},
        )
        AccessPermission.objects.get_or_create(
            module=self.category_module,
            code="categories.create",
            defaults={"action": "create", "name": "Create categories"},
        )

    def test_platform_admin_can_create_tenant_with_admin_user(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.post(
            "/api/tenants/",
            {
                "name": "Radha Catering",
                "schema_name": "radha",
                "subscription_status": "active",
                "enabled_modules": ["categories", "users"],
                "admin": {
                    "username": "radha-admin",
                    "email": "admin@radha.example",
                    "password": "admin1234",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["schema_name"], "radha")
        expected_schema_status = (
            Tenant.SCHEMA_READY
            if connection.vendor == "postgresql"
            else Tenant.SCHEMA_SKIPPED
        )
        self.assertEqual(response.data["data"]["schema_status"], expected_schema_status)

        tenant = Tenant.objects.get(schema_name="radha")
        tenant_admin = UserModel.objects.get(username="radha-admin")
        self.assertEqual(tenant_admin.tenant, tenant)
        self.assertTrue(tenant_admin.is_staff)

    def test_tenant_admin_can_create_module_scoped_user(self):
        tenant = Tenant.objects.create(
            name="Radha",
            schema_name="radha",
            subscription_status=Tenant.STATUS_ACTIVE,
        )
        tenant.enabled_modules.set([self.category_module, self.users_module])
        tenant_admin = UserModel.objects.create_user(
            username="radha-admin",
            password="admin1234",
            is_staff=True,
            tenant=tenant,
        )
        self.client.force_authenticate(user=tenant_admin)

        response = self.client.post(
            "/api/users/",
            {
                "username": "radha-manager",
                "email": "manager@radha.example",
                "password": "manager1234",
                "module_codes": ["categories"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        created_user = UserModel.objects.get(username="radha-manager")
        self.assertEqual(created_user.tenant, tenant)
        self.assertTrue(
            UserPermissionAssignment.objects.filter(
                user=created_user,
                permission__code="categories.view",
                is_allowed=True,
            ).exists()
        )
