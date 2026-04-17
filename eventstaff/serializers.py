from decimal import Decimal

from rest_framework import serializers

from .models import (
    EventStaffAssignment,
    FixedStaffSalaryPayment,
    Staff,
    StaffRole,
    WaiterType,
    StaffWithdrawal,
    add_months,
    normalize_salary_month,
)


class StaffWithdrawalSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.name", read_only=True)

    class Meta:
        model = StaffWithdrawal
        fields = (
            "id",
            "staff",
            "staff_name",
            "amount",
            "payment_date",
            "note",
            "is_adjusted",
            "adjusted_in_payment",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("is_adjusted", "adjusted_in_payment", "created_at", "updated_at")



class StaffRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRole
        fields = "__all__"


class WaiterTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaiterType
        fields = "__all__"


class StaffSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    waiter_type_name = serializers.CharField(source="waiter_type.name", read_only=True)

    class Meta:
        model = Staff
        fields = "__all__"
        extra_kwargs = {
            "role": {"help_text": "ID of the StaffRole from /eventstaff/roles/"},
            "waiter_type": {
                "help_text": "ID of the WaiterType from /eventstaff/waiter-types/"
            },
            "staff_type": {"help_text": "Type of employment (Fixed, Agency, Contract)"},
            "per_person_rate": {
                "help_text": "Default rate charged per person for this staff member"
            },
        }


class EventStaffAssignmentSerializer(serializers.ModelSerializer):
    # Optional nested details for GET endpoints
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    staff_type = serializers.CharField(source="staff.staff_type", read_only=True)
    session_name = serializers.CharField(source="session.booking.name", read_only=True)
    session_date = serializers.CharField(source="session.event_date", read_only=True)
    role_name_at_event = serializers.CharField(
        source="role_at_event.name", read_only=True
    )

    class Meta:
        model = EventStaffAssignment
        fields = "__all__"
        read_only_fields = (
            "total_amount",
            "remaining_amount",
            "payment_status",
            "created_at",
            "updated_at",
        )

    def validate(self, data):
        """
        Custom validation to prevent invalid values.
        """
        paid_amount = data.get("paid_amount", 0)
        total_days = data.get("total_days", 1)
        per_person_rate = data.get("per_person_rate")

        # Check for negative values
        if paid_amount and paid_amount < 0:
            raise serializers.ValidationError(
                {"paid_amount": "Paid amount cannot be negative."}
            )
    # Optional nested details for GET endpoints
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    staff_type = serializers.CharField(source="staff.staff_type", read_only=True)
    session_name = serializers.CharField(source="session.booking.name", read_only=True)
    session_date = serializers.CharField(source="session.event_date", read_only=True)
    role_name_at_event = serializers.CharField(
        source="role_at_event.name", read_only=True
    )

    class Meta:
        model = EventStaffAssignment
        fields = "__all__"
        read_only_fields = (
            "total_amount",
            "remaining_amount",
            "payment_status",
            "created_at",
            "updated_at",
        )

    def validate(self, data):
        """
        Custom validation to prevent invalid values.
        """
        paid_amount = data.get("paid_amount", 0)
        total_days = data.get("total_days", 1)
        per_person_rate = data.get("per_person_rate")

        # Check for negative values
        if paid_amount and paid_amount < 0:
            raise serializers.ValidationError(
                {"paid_amount": "Paid amount cannot be negative."}
            )

        if total_days and total_days <= 0:
            raise serializers.ValidationError(
                {"total_days": "Total days must be greater than zero."}
            )

        if per_person_rate is not None and per_person_rate < 0:
            raise serializers.ValidationError(
                {"per_person_rate": "Per person rate cannot be negative."}
            )

        staff = data.get("staff")
        if not staff and self.instance:
            staff = self.instance.staff

        if staff:
            if staff.staff_type == "Fixed":
                calc_amount = Decimal("0.00")
            else:
                calc_rate = (
                    per_person_rate
                    if per_person_rate is not None
                    else staff.per_person_rate
                )
                number_of_persons = data.get("number_of_persons", getattr(self.instance, 'number_of_persons', 1))
                calc_amount = calc_rate * total_days * number_of_persons

            # Only validate if paid_amount is provided, or if instance already has paid_amount
            if paid_amount is not None and paid_amount > calc_amount:
                raise serializers.ValidationError(
                    {"paid_amount": "Paid amount cannot exceed total amount."}
                )

        return data


class FixedStaffSalaryPaymentSerializer(serializers.ModelSerializer):
    start_date = serializers.DateField(
        input_formats=["%d-%m-%Y", "%Y-%m-%d"],
        format="%d-%m-%Y",
    )
    end_date = serializers.DateField(
        input_formats=["%d-%m-%Y", "%Y-%m-%d"],
        format="%d-%m-%Y",
    )
    payment_date = serializers.DateField(
        input_formats=["%d-%m-%Y", "%Y-%m-%d"],
        format="%d-%m-%Y",
        required=False,
        allow_null=True,
    )
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    staff_type = serializers.CharField(source="staff.staff_type", read_only=True)
    role_name = serializers.CharField(source="staff.role.name", read_only=True)
    covered_month_label = serializers.ReadOnlyField()

    class Meta:
        model = FixedStaffSalaryPayment
        fields = (
            "id",
            "staff",
            "staff_name",
            "staff_type",
            "role_name",
            "start_date",
            "end_date",
            "covered_month_label",
            "months_count",
            "monthly_salary",
            "total_amount",
            "withdrawal_deduction",
            "paid_amount",
            "remaining_amount",
            "payment_status",
            "payment_date",
            "note",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "monthly_salary",
            "total_amount",
            "withdrawal_deduction",
            "remaining_amount",
            "payment_status",
            "created_at",
            "updated_at",
        )

    def validate(self, data):
        staff = data.get("staff", getattr(self.instance, "staff", None))
        start_date = data.get("start_date", getattr(self.instance, "start_date", None))
        end_date = data.get("end_date", getattr(self.instance, "end_date", None))
        months_count = data.get("months_count", getattr(self.instance, "months_count", Decimal("1.0")))
        paid_amount = data.get(
            "paid_amount",
            getattr(self.instance, "paid_amount", Decimal("0.00")),
        )

        if not staff:
            raise serializers.ValidationError({"staff": "Staff is required."})

        if staff.staff_type != "Fixed":
            raise serializers.ValidationError(
                {"staff": "Monthly salary payments are only allowed for Fixed staff."}
            )

        fixed_salary = staff.fixed_salary or Decimal("0.00")
        if fixed_salary <= 0:
            raise serializers.ValidationError(
                {"staff": "This fixed staff does not have a valid monthly salary."}
            )

        if not start_date or not end_date:
            raise serializers.ValidationError(
                {"start_date": "Start and End dates are required."}
            )
            
        if start_date > end_date:
            raise serializers.ValidationError(
                {"end_date": "End date cannot be before start date."}
            )

        if months_count <= 0:
            raise serializers.ValidationError(
                {"months_count": "Months count must be greater than zero."}
            )

        if paid_amount < 0:
            raise serializers.ValidationError(
                {"paid_amount": "Paid amount cannot be negative."}
            )

        total_amount = fixed_salary * Decimal(str(months_count))
        # Remove total_amount check since withdrawal_deduction + paid_amount equals total_amount
        # We handle this strictly in the view's perform_create.
        if paid_amount > total_amount:
            raise serializers.ValidationError(
                {"paid_amount": "Final paid amount cannot exceed gross salary amount."}
            )

        overlapping_payment = self._get_overlapping_payment(
            staff=staff,
            start_date=start_date,
            end_date=end_date,
        )
        if overlapping_payment:
            raise serializers.ValidationError(
                {
                    "start_date": (
                        "This salary period overlaps with an existing payment record."
                    )
                }
            )

        return data

    def _get_overlapping_payment(self, staff, start_date, end_date):
        payments = FixedStaffSalaryPayment.objects.filter(staff=staff)
        if self.instance:
            payments = payments.exclude(pk=self.instance.pk)

        for payment in payments:
            if start_date <= payment.end_date and payment.start_date <= end_date:
                return payment

        return None
