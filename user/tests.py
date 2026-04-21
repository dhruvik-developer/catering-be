from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)


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
        self.assertEqual(str(response.data["detail"]), "Only admin can create this resource.")
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
        self.assertEqual(response.data["message"], "User List Fatch successfully.")
