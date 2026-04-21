from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accesscontrol.models import AccessPermission
from eventstaff.models import Staff
from vendor.models import Vendor


UserModel = get_user_model()


class AccessControlTests(APITestCase):
    def setUp(self):
        self.admin = UserModel.objects.create_user(
            username="admin",
            password="admin1234",
            is_staff=True,
            is_superuser=True,
        )
        login_response = self.client.post(
            "/api/login/",
            {"username": "admin", "password": "admin1234"},
            format="json",
        )
        self.admin_token = login_response.data["data"]["tokens"]["access"]
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}

    def test_vendor_direct_permissions_control_list_and_create_access(self):
        vendor_user = UserModel.objects.create_user(
            username="vendor-user",
            password="vendor1234",
        )
        Vendor.objects.create(name="Vendor One", user_account=vendor_user, is_active=True)

        permissions_payload = {
            "allowed_permissions": ["vendors.view"],
            "denied_permissions": [],
        }
        response = self.client.put(
            f"/api/access-control/users/{vendor_user.id}/permissions/",
            permissions_payload,
            format="json",
            **self.admin_headers,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        login_response = self.client.post(
            "/api/login/",
            {"username": "vendor-user", "password": "vendor1234"},
            format="json",
        )
        self.assertIn("vendors.view", login_response.data["data"]["permissions"])

        vendor_token = login_response.data["data"]["tokens"]["access"]
        vendor_headers = {"HTTP_AUTHORIZATION": f"Bearer {vendor_token}"}

        list_response = self.client.get("/api/vendors/", **vendor_headers)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            "/api/vendors/",
            {"name": "Vendor Two", "mobile_no": "9999999999", "address": "", "vendor_categories": []},
            format="json",
            **vendor_headers,
        )
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_direct_permission_and_user_deny_override(self):
        staff_user = UserModel.objects.create_user(
            username="staff-user",
            password="staff1234",
        )
        Staff.objects.create(name="Staff One", user_account=staff_user, is_active=True)

        assign_response = self.client.put(
            f"/api/access-control/users/{staff_user.id}/permissions/",
            {
                "allowed_permissions": ["staff.view"],
                "denied_permissions": [],
            },
            format="json",
            **self.admin_headers,
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)

        login_response = self.client.post(
            "/api/login/",
            {"username": "staff-user", "password": "staff1234"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("staff.view", login_response.data["data"]["permissions"])

        staff_token = login_response.data["data"]["tokens"]["access"]
        staff_headers = {"HTTP_AUTHORIZATION": f"Bearer {staff_token}"}

        list_response = self.client.get("/api/staff/", **staff_headers)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        deny_response = self.client.put(
            f"/api/access-control/users/{staff_user.id}/permissions/",
            {
                "allowed_permissions": [],
                "denied_permissions": ["staff.view"],
            },
            format="json",
            **self.admin_headers,
        )
        self.assertEqual(deny_response.status_code, status.HTTP_200_OK)

        denied_list_response = self.client.get("/api/staff/", **staff_headers)
        self.assertEqual(denied_list_response.status_code, status.HTTP_403_FORBIDDEN)
