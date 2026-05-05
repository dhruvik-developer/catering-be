from datetime import date as current_date
from decimal import Decimal

import django.utils.timezone
from django.conf import settings
from django.db import models

from eventbooking.models import EventSession


def normalize_salary_month(value):
    if value is None:
        return None
    return value.replace(day=1)


def add_months(value, months):
    normalized_value = normalize_salary_month(value)
    month_index = normalized_value.month - 1 + months
    year = normalized_value.year + month_index // 12
    month = month_index % 12 + 1
    return normalized_value.replace(year=year, month=month, day=1)


class StaffRole(models.Model):
    name = models.CharField("Role Name", max_length=100, unique=True)
    description = models.TextField("Role Description", blank=True, null=True)

    created_at = models.DateTimeField(default=django.utils.timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Role"
        verbose_name_plural = "Staff Roles"

    def __str__(self):
        return self.name


class StaffRolePermissionAssignment(models.Model):
    role = models.ForeignKey(
        StaffRole,
        on_delete=models.CASCADE,
        related_name="permission_assignments",
    )
    permission = models.ForeignKey(
        "accesscontrol.AccessPermission",
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


class WaiterType(models.Model):
    name = models.CharField("Waiter Type", max_length=120, unique=True)
    description = models.TextField("Description", blank=True, null=True)
    per_person_rate = models.DecimalField(
        "Per Person Rate",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Default per person rate for this waiter type",
    )
    is_active = models.BooleanField("Is Active", default=True)

    created_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Waiter Type"
        verbose_name_plural = "Waiter Types"

    def __str__(self):
        return f"{self.name} ({self.per_person_rate})"


class Staff(models.Model):
    STAFF_TYPE_CHOICES = (
        ("Fixed", "Fixed"),
        ("Agency", "Agency"),
        ("Contract", "Contract"),
    )

    user_account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="staff_profile",
        verbose_name="Login User",
        help_text="Optional login account for this staff member.",
    )
    name = models.CharField("Staff Name", max_length=150)
    phone = models.CharField("Phone Number", max_length=20, blank=True, null=True)
    role = models.ForeignKey(
        StaffRole,
        on_delete=models.SET_NULL,
        verbose_name="Role",
        blank=True,
        null=True,
    )
    staff_type = models.CharField(
        "Staff Type", max_length=20, choices=STAFF_TYPE_CHOICES, default="Contract"
    )

    fixed_salary = models.DecimalField(
        "Fixed Salary", max_digits=10, decimal_places=2, blank=True, null=True
    )
    waiter_type = models.ForeignKey(
        "WaiterType",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Waiter Type",
        help_text="Type of waiter service (VIP, VVIP, Normal, Special Couple, etc)",
    )
    per_person_rate = models.DecimalField(
        "Paid Per Person (Rate)", max_digits=10, decimal_places=2, default=0.00
    )
    is_active = models.BooleanField("Is Active", default=True)
    joining_date = models.DateField(
        "Joining Date",
        default=django.utils.timezone.localdate,
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="staff_created",
        verbose_name="Created By",
    )

    created_at = models.DateTimeField(default=django.utils.timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff"
        verbose_name_plural = "Staff Members"

    def __str__(self):
        waiter_category = (
            self.waiter_type.name if self.waiter_type else "No Waiter Type"
        )
        login_label = (
            self.user_account.username if self.user_account else "No Login"
        )
        return (
            f"{self.name} ({self.role.name if self.role else 'Unassigned'} - "
            f"{self.staff_type} - {waiter_category} - {login_label})"
        )

    def save(self, *args, **kwargs):
        if self.user_account:
            if not self.user_account.first_name:
                self.user_account.first_name = self.name
            self.user_account.is_active = self.is_active
            self.user_account.save(update_fields=["first_name", "is_active"])
        super().save(*args, **kwargs)


class StaffWithdrawal(models.Model):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="withdrawals",
        verbose_name="Staff",
    )
    amount = models.DecimalField(
        "Withdrawal Amount", max_digits=12, decimal_places=2, default=0.00
    )
    payment_date = models.DateField("Payment Date", default=django.utils.timezone.now)
    note = models.TextField("Note", blank=True, null=True)
    is_adjusted = models.BooleanField("Adjusted in Salary?", default=False)
    adjusted_in_payment = models.ForeignKey(
        "FixedStaffSalaryPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="covered_withdrawals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Withdrawal"
        verbose_name_plural = "Staff Withdrawals"
        ordering = ("-payment_date", "-created_at")

    def __str__(self):
        return f"{self.staff.name} - Rs. {self.amount} on {self.payment_date}"


class EventStaffAssignment(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ("Pending", "Pending"),
        ("Partial", "Partial"),
        ("Paid", "Paid"),
    )

    session = models.ForeignKey(
        EventSession,
        on_delete=models.CASCADE,
        related_name="staff_assignments",
        verbose_name="Session",
        null=True,
        blank=True,
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="event_assignments",
        verbose_name="Staff",
    )

    role_at_event = models.ForeignKey(
        StaffRole,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Role at Event",
        help_text="Override default role for this specific event if needed",
    )
    total_days = models.DecimalField(
        "Total Days", max_digits=5, decimal_places=1, default=1.0
    )
    number_of_persons = models.PositiveIntegerField(
        "Number of Persons",
        default=1,
        help_text="Number of staff members supplied by agency/contractor",
    )
    per_person_rate = models.DecimalField(
        "Per Person Rate (Override)",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Leave blank to use staff's default rate",
    )

    total_amount = models.DecimalField(
        "Total Amount", max_digits=10, decimal_places=2, default=0.00, editable=False
    )
    paid_amount = models.DecimalField(
        "Paid Amount", max_digits=10, decimal_places=2, default=0.00
    )
    remaining_amount = models.DecimalField(
        "Remaining Amount",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        editable=False,
    )
    payment_status = models.CharField(
        "Payment Status",
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="Pending",
        editable=False,
    )

    created_at = models.DateTimeField(default=django.utils.timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Event Staff Assignment"
        verbose_name_plural = "Event Staff Assignments"
        unique_together = ("session", "staff")

    def __str__(self):
        booking_name = (
            self.session.booking.name if hasattr(self.session, "booking") else "Unknown"
        )
        return f"{self.staff.name} at {booking_name} ({self.session.event_date})"

    def save(self, *args, **kwargs):
        if self.staff.staff_type == "Fixed":
            self.total_amount = Decimal("0.00")
            if self.per_person_rate is not None:
                self.per_person_rate = None
        else:
            effective_rate = (
                self.per_person_rate
                if self.per_person_rate is not None
                else self.staff.per_person_rate
            )
            effective_rate = Decimal(str(effective_rate or 0))
            self.total_amount = (
                Decimal(str(self.total_days))
                * effective_rate
                * Decimal(str(self.number_of_persons))
            )

        if self.paid_amount is None:
            self.paid_amount = Decimal("0.00")
        else:
            self.paid_amount = Decimal(str(self.paid_amount))

        self.remaining_amount = self.total_amount - self.paid_amount

        if self.paid_amount <= 0:
            self.payment_status = "Pending"
        elif self.paid_amount >= self.total_amount:
            self.payment_status = "Paid"
        else:
            self.payment_status = "Partial"

        if not self.role_at_event:
            self.role_at_event = self.staff.role

        super().save(*args, **kwargs)


class FixedStaffSalaryPayment(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ("Pending", "Pending"),
        ("Partial", "Partial"),
        ("Paid", "Paid"),
    )

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="salary_payments",
        verbose_name="Fixed Staff",
        limit_choices_to={"staff_type": "Fixed"},
    )
    start_date = models.DateField(
        "Start Date",
        default=django.utils.timezone.now,
    )
    end_date = models.DateField(
        "End Date",
        default=django.utils.timezone.now,
    )
    months_count = models.DecimalField(
        "Months Count", max_digits=5, decimal_places=2, default=1.0
    )
    monthly_salary = models.DecimalField(
        "Monthly Salary",
        max_digits=10,
        decimal_places=2,
        default=0.00,
        editable=False,
    )
    total_amount = models.DecimalField(
        "Total Gross Amount",
        max_digits=12,
        decimal_places=2,
        default=0.00,
        editable=False,
    )
    withdrawal_deduction = models.DecimalField(
        "Withdrawal Deduction",
        max_digits=12,
        decimal_places=2,
        default=0.00,
        editable=False,
    )
    paid_amount = models.DecimalField(
        "Final Paid Amount", max_digits=12, decimal_places=2, default=0.00
    )
    remaining_amount = models.DecimalField(
        "Remaining Amount",
        max_digits=12,
        decimal_places=2,
        default=0.00,
        editable=False,
    )
    payment_status = models.CharField(
        "Payment Status",
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="Pending",
        editable=False,
    )
    payment_date = models.DateField("Payment Date", blank=True, null=True)
    note = models.TextField("Note", blank=True, null=True)

    created_at = models.DateTimeField(default=django.utils.timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fixed Staff Salary Payment"
        verbose_name_plural = "Fixed Staff Salary Payments"
        ordering = ("-start_date", "-created_at")

    def __str__(self):
        return f"{self.staff.name} salary for {self.covered_month_label}"

    @property
    def period_end_month(self):
        return self.end_date

    @property
    def covered_month_label(self):
        if not self.start_date or not self.end_date:
            return ""

        start_label = self.start_date.strftime("%d %b %Y")
        end_label = self.end_date.strftime("%d %b %Y")

        if start_label == end_label:
            return start_label

        return f"{start_label} - {end_label}"

    def save(self, *args, **kwargs):
        if self.staff and self.staff.staff_type != "Fixed":
            raise ValueError(
                "Fixed staff salary payments can only be created for Fixed staff."
            )
        self.monthly_salary = (
            self.staff.fixed_salary
            if self.staff and self.staff.fixed_salary
            else Decimal("0.00")
        )

        if self.paid_amount is None:
            self.paid_amount = Decimal("0.00")
        else:
            self.paid_amount = Decimal(str(self.paid_amount))

        if self.withdrawal_deduction is None:
            self.withdrawal_deduction = Decimal("0.00")
        else:
            self.withdrawal_deduction = Decimal(str(self.withdrawal_deduction))

        self.total_amount = self.monthly_salary * Decimal(str(self.months_count or 0))
        self.remaining_amount = (
            self.total_amount
            - self.withdrawal_deduction
            - Decimal(str(self.paid_amount))
        )

        if self.remaining_amount < 0:
            self.remaining_amount = Decimal("0.00")

        if self.paid_amount == 0 and self.withdrawal_deduction == 0:
            self.payment_status = "Pending"
        elif self.remaining_amount <= 0:
            self.payment_status = "Paid"
        else:
            self.payment_status = "Partial"

        if self.paid_amount > 0 and not self.payment_date:
            self.payment_date = current_date.today()

        super().save(*args, **kwargs)
