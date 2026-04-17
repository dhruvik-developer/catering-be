from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from eventbooking.models import EventBooking, EventSession

from .models import EventStaffAssignment, Staff, StaffRole


class FixedStaffSalaryPaymentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="password123",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

        self.role = StaffRole.objects.create(name="Cleaner")
        self.fixed_staff = Staff.objects.create(
            name="Staff 98",
            phone="9999990098",
            role=self.role,
            staff_type="Fixed",
            per_person_rate=Decimal("187.00"),
            fixed_salary=Decimal("15174.00"),
        )
        self.booking = EventBooking.objects.create(
            name="Fixed Staff Event",
            mobile_no="9999999999",
            reference="fixed-ref-1",
        )
        self.session = EventSession.objects.create(
            booking=self.booking,
            event_date=date(2026, 3, 18),
            event_time="10:00 AM",
            event_address="Test Address",
        )

    def test_create_salary_payment_and_fetch_fixed_staff_summary(self):
        EventStaffAssignment.objects.create(
            session=self.session,
            staff=self.fixed_staff,
            role_at_event=self.role,
            paid_amount=Decimal("500.00"),
        )

        create_response = self.client.post(
            reverse("fixed-salary-payment-list"),
            {
                "staff": self.fixed_staff.id,
                "salary_month": "01-03-2026",
                "months_count": 2,
                "paid_amount": "15174.00",
                "payment_date": "20-03-2026",
                "note": "First month released",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["payment_status"], "Partial")
        self.assertEqual(create_response.data["total_amount"], "30348.00")
        self.assertEqual(create_response.data["remaining_amount"], "15174.00")

        summary_response = self.client.get(
            reverse("staff-fixed-payment-summary", args=[self.fixed_staff.id])
        )

        self.assertEqual(summary_response.status_code, status.HTTP_200_OK)
        self.assertTrue(summary_response.data["status"])
        self.assertEqual(summary_response.data["data"]["total_salary_months"], 2)
        self.assertEqual(
            summary_response.data["data"]["total_salary_amount"], "30348.00"
        )
        self.assertEqual(
            summary_response.data["data"]["total_salary_paid"], "15174.00"
        )
        self.assertEqual(
            summary_response.data["data"]["total_salary_pending"], "15174.00"
        )
        self.assertEqual(
            summary_response.data["data"]["paid_months_equivalent"], "1.00"
        )
        self.assertEqual(summary_response.data["data"]["total_event_paid"], "500.00")
        self.assertEqual(summary_response.data["data"]["total_overall_paid"], "15674.00")
        self.assertEqual(len(summary_response.data["data"]["salary_payments"]), 1)
        self.assertEqual(len(summary_response.data["data"]["event_payments"]), 1)
