from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Staff


class StaffRegistrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_public_staff_registration_auto_activates_and_can_login(self):
        register_response = self.client.post(
            "/api/staff/register/",
            {
                "name": "Raju",
                "phone": "9876543210",
                "login_username": "staff-register-user",
                "login_password": "staff1234",
                "login_email": "staff@example.com",
            },
            format="json",
        )

        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(register_response.data["status"])
        self.assertEqual(
            register_response.data["message"],
            "Registration successful. You can log in now.",
        )

        staff = Staff.objects.get(name="Raju")
        self.assertTrue(staff.is_active)
        self.assertIsNotNone(staff.user_account)
        self.assertTrue(staff.user_account.is_active)

        login_response = self.client.post(
            "/api/login/",
            {
                "username": "staff-register-user",
                "password": "staff1234",
            },
            format="json",
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertTrue(login_response.data["status"])
        self.assertEqual(
            login_response.data["data"]["username"],
            "staff-register-user",
        )
