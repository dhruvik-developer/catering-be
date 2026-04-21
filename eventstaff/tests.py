from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)
from eventstaff.models import Staff


UserModel = get_user_model()


class StaffAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = UserModel.objects.create_superuser(
            username="admin-staff",
            email="admin-staff@example.com",
            password="admin1234",
        )
        self.manager = UserModel.objects.create_user(
            username="manager-staff",
            email="manager-staff@example.com",
            password="manager1234",
        )

        module, _ = PermissionModule.objects.get_or_create(
            code="staff",
            defaults={"name": "Staff"},
        )
        create_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="staff.create",
            defaults={
                "action": "create",
                "name": "Create Staff",
            },
        )
        view_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="staff.view",
            defaults={
                "action": "view",
                "name": "View Staff",
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

        self.existing_staff = Staff.objects.create(name="Existing Staff")

    def test_non_admin_cannot_create_staff_even_with_create_permission(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/staff/",
            {
                "name": "Blocked Staff",
                "phone": "9876543210",
                "staff_type": "Contract",
                "per_person_rate": "250.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(str(response.data["detail"]), "Only admin can create this resource.")
        self.assertFalse(Staff.objects.filter(name="Blocked Staff").exists())

    def test_admin_can_create_staff(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/staff/",
            {
                "name": "Admin Staff",
                "phone": "9876543210",
                "staff_type": "Contract",
                "per_person_rate": "250.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Admin Staff")
        self.assertTrue(Staff.objects.filter(name="Admin Staff").exists())

    def test_non_admin_with_view_permission_can_still_list_staff(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get("/api/staff/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_staff_public_registration_route_is_disabled(self):
        response = self.client.post(
            "/api/staff/register/",
            {
                "name": "Public Staff",
                "phone": "9876543210",
                "login_username": "public-staff",
                "login_password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
