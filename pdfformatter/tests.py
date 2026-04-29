from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import PdfFormatter


UserModel = get_user_model()


class PdfFormatterAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = UserModel.objects.create_superuser(
            username="pdf-admin",
            email="pdf-admin@example.com",
            password="admin1234",
        )
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_create_pdf_formatter_with_html_content(self):
        response = self.client.post(
            "/api/pdf-formatters/",
            {
                "name": "Invoice Format",
                "description": "Default invoice PDF view",
                "html_content": "<html><body><h1>{{ invoice_number }}</h1></body></html>",
                "sample_data": {"invoice_number": "INV-001"},
                "is_default": True,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["status"])
        self.assertEqual(response.data["data"]["code"], "invoice-format")
        self.assertEqual(str(response.data["data"]["created_by"]), str(self.admin.id))
        self.assertTrue(PdfFormatter.objects.filter(code="invoice-format").exists())

    def test_html_preview_returns_stored_html(self):
        formatter = PdfFormatter.objects.create(
            name="Event Summary",
            html_content="<html><body>Event summary</body></html>",
            created_by=self.admin,
        )

        response = self.client.get(f"/api/pdf-formatters/{formatter.id}/html/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/html", response["Content-Type"])
        self.assertEqual(response.content.decode(), formatter.html_content)

    def test_default_formatter_is_unique(self):
        first = PdfFormatter.objects.create(
            name="First Format",
            html_content="<html>First</html>",
            is_default=True,
        )
        second = PdfFormatter.objects.create(
            name="Second Format",
            html_content="<html>Second</html>",
            is_default=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
