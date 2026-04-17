from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from Expense.models import Category, Expense
from eventbooking.models import EventBooking, EventSession
from eventstaff.models import (
    EventStaffAssignment,
    FixedStaffSalaryPayment,
    Staff,
    StaffRole,
)

from .models import Payment


class AllTransactionSummaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="transaction-admin",
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
            name="Transaction Event",
            mobile_no="9999999999",
            reference="transaction-ref-1",
        )
        self.session = EventSession.objects.create(
            booking=self.booking,
            event_date=date(2026, 3, 18),
            event_time="10:00 AM",
            event_address="Transaction Address",
        )

    def test_all_transaction_includes_fixed_salary_paid_amount(self):
        Payment.objects.create(
            total_amount=Decimal("10000"),
            total_extra_amount=Decimal("0"),
            advance_amount=Decimal("10000"),
            pending_amount=Decimal("0"),
            payment_date=date(2026, 3, 18),
            transaction_amount=Decimal("10000"),
            payment_mode="CASH",
            settlement_amount=Decimal("0"),
            payment_status="PAID",
            note="Fully paid booking",
        )

        category = Category.objects.create(name="General")
        Expense.objects.create(
            title="Office Expense",
            amount=Decimal("100.00"),
            category=category,
            payment_mode="CASH",
        )

        EventStaffAssignment.objects.create(
            session=self.session,
            staff=self.fixed_staff,
            role_at_event=self.role,
            paid_amount=Decimal("200.00"),
        )

        FixedStaffSalaryPayment.objects.create(
            staff=self.fixed_staff,
            salary_month=date(2026, 3, 1),
            months_count=1,
            paid_amount=Decimal("3000.00"),
            payment_date=date(2026, 3, 20),
        )

        response = self.client.get("/api/all-transaction/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["status"])
        self.assertEqual(response.data["data"]["total_expense_amount"], 3300)
        self.assertEqual(response.data["data"]["net_amount"], 6700)
