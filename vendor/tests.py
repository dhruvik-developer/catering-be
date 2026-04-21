from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)
from vendor.models import Vendor


UserModel = get_user_model()


class VendorAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = UserModel.objects.create_superuser(
            username="admin-vendor",
            email="admin-vendor@example.com",
            password="admin1234",
        )
        self.manager = UserModel.objects.create_user(
            username="manager-vendor",
            email="manager-vendor@example.com",
            password="manager1234",
        )

        module, _ = PermissionModule.objects.get_or_create(
            code="vendors",
            defaults={"name": "Vendors"},
        )
        create_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="vendors.create",
            defaults={
                "action": "create",
                "name": "Create Vendor",
            },
        )
        view_permission, _ = AccessPermission.objects.get_or_create(
            module=module,
            code="vendors.view",
            defaults={
                "action": "view",
                "name": "View Vendor",
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

        self.existing_vendor = Vendor.objects.create(name="Existing Vendor")

    def test_non_admin_cannot_create_vendor_even_with_create_permission(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/vendors/",
            {
                "name": "Blocked Vendor",
                "mobile_no": "9999999999",
                "address": "Somewhere",
                "is_active": True,
                "vendor_categories": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(str(response.data["detail"]), "Only admin can create this resource.")
        self.assertFalse(Vendor.objects.filter(name="Blocked Vendor").exists())

    def test_admin_can_create_vendor(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/vendors/",
            {
                "name": "Admin Vendor",
                "mobile_no": "8888888888",
                "address": "HQ",
                "is_active": True,
                "vendor_categories": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["status"])
        self.assertTrue(Vendor.objects.filter(name="Admin Vendor").exists())

    def test_non_admin_with_view_permission_can_still_list_vendors(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get("/api/vendors/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])

    def test_vendor_public_registration_route_is_disabled(self):
        response = self.client.post(
            "/api/vendors/register/",
            {
                "name": "Public Vendor",
                "login_username": "public-vendor",
                "login_password": "pass1234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
