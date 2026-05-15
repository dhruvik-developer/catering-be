from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import (
    EventStaffAssignment,
    FixedStaffSalaryPayment,
    Staff,
    StaffRole,
    StaffWithdrawal,
    WaiterType,
)


UserModel = get_user_model()
MIN_LOGIN_PASSWORD_LENGTH = 8


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
        read_only_fields = (
            "is_adjusted",
            "adjusted_in_payment",
            "created_at",
            "updated_at",
        )


class StaffRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRole
        fields = "__all__"
        read_only_fields = ("branch_profile",)


class WaiterTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaiterType
        fields = "__all__"
        read_only_fields = ("branch_profile",)


class StaffSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    waiter_type_name = serializers.CharField(source="waiter_type.name", read_only=True)
    linked_user_id = serializers.UUIDField(source="user_account.id", read_only=True)
    linked_username = serializers.CharField(
        source="user_account.username",
        read_only=True,
    )
    login_enabled = serializers.SerializerMethodField()
    login_username = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    login_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    login_email = serializers.EmailField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = Staff
        fields = (
            "id",
            "user_account",
            "linked_user_id",
            "linked_username",
            "login_enabled",
            "login_username",
            "login_password",
            "login_email",
            "branch_profile",
            "name",
            "phone",
            "role",
            "role_name",
            "staff_type",
            "fixed_salary",
            "waiter_type",
            "waiter_type_name",
            "per_person_rate",
            "agency_services",
            "is_active",
            "joining_date",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "user_account",
            "linked_user_id",
            "linked_username",
            "login_enabled",
            "branch_profile",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
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

    def get_login_enabled(self, obj):
        return obj.user_account_id is not None

    def validate(self, attrs):
        username = attrs.get("login_username")
        password = attrs.get("login_password")
        existing_user = getattr(self.instance, "user_account", None)

        if username == "":
            username = None
        if password == "":
            password = None

        if username and not existing_user and not password:
            raise serializers.ValidationError(
                {"login_password": "Password is required when creating a staff login."}
            )

        if password and len(password) < MIN_LOGIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                {
                    "login_password": (
                        f"Password must be at least {MIN_LOGIN_PASSWORD_LENGTH} "
                        "characters long."
                    )
                }
            )

        if username:
            users = UserModel.objects.filter(username=username)
            if existing_user:
                users = users.exclude(pk=existing_user.pk)
            if users.exists():
                raise serializers.ValidationError(
                    {"login_username": "This username is already in use."}
                )

        # New logic for employment type validation
        staff_type = attrs.get("staff_type", getattr(self.instance, "staff_type", "Contract"))

        if staff_type == "Fixed":
            fixed_salary = attrs.get("fixed_salary", getattr(self.instance, "fixed_salary", None))
            if not fixed_salary or Decimal(str(fixed_salary)) <= 0:
                raise serializers.ValidationError(
                    {"fixed_salary": "Fixed salary is required and must be greater than 0."}
                )
        elif staff_type == "Contract":
            per_person_rate = attrs.get("per_person_rate", getattr(self.instance, "per_person_rate", 0))
            if not per_person_rate or Decimal(str(per_person_rate)) <= 0:
                raise serializers.ValidationError(
                    {"per_person_rate": "Per person rate is required and must be greater than 0."}
                )
        elif staff_type == "Agency":
            agency_services = attrs.get("agency_services", getattr(self.instance, "agency_services", []))
            valid_services = [
                s for s in agency_services
                if s.get("service_name") and s.get("service_name").strip() and Decimal(str(s.get("rate", 0))) > 0
            ]
            if not valid_services:
                raise serializers.ValidationError(
                    {"agency_services": "Add at least one service with a name and rate greater than 0."}
                )

        return attrs

    def _upsert_login_user(self, staff, validated_data):
        username = validated_data.pop("login_username", None)
        password = validated_data.pop("login_password", None)
        email = validated_data.pop("login_email", None)

        username = username or None
        password = password or None
        email = email or ""

        linked_user = staff.user_account
        if not username and not linked_user:
            return

        if linked_user is None and username:
            linked_user = UserModel.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=staff.name,
                is_active=staff.is_active,
                branch_profile=staff.branch_profile,
                branch_role=UserModel.BRANCH_ROLE_BRANCH_USER,
            )
            staff.user_account = linked_user
            staff.save(update_fields=["user_account", "updated_at"])
            return

        if linked_user is not None:
            if username:
                linked_user.username = username
            if "login_email" in self.initial_data:
                linked_user.email = email
            linked_user.first_name = staff.name
            linked_user.is_active = staff.is_active
            linked_user.branch_profile = staff.branch_profile
            if password:
                linked_user.set_password(password)
            linked_user.save()

    def create(self, validated_data):
        request = self.context.get("request")
        if request is None or not (
            request.user.is_superuser or request.user.is_staff
        ):
            raise PermissionDenied("Only admin allowed.")

        branch_profile = validated_data.get("branch_profile")
        role = validated_data.get("role")
        waiter_type = validated_data.get("waiter_type")
        if role and role.branch_profile_id != getattr(branch_profile, "id", None):
            raise serializers.ValidationError(
                {"role": "Staff role must belong to the selected branch."}
            )
        if waiter_type and waiter_type.branch_profile_id != getattr(branch_profile, "id", None):
            raise serializers.ValidationError(
                {"waiter_type": "Waiter type must belong to the selected branch."}
            )

        staff = Staff.objects.create(
            created_by=request.user,
            **{
                key: value
                for key, value in validated_data.items()
                if key not in {"login_username", "login_password", "login_email"}
            }
        )
        self._upsert_login_user(staff, validated_data)
        return staff

    def update(self, instance, validated_data):
        branch_profile = validated_data.get("branch_profile", instance.branch_profile)
        role = validated_data.get("role", instance.role)
        waiter_type = validated_data.get("waiter_type", instance.waiter_type)
        if role and role.branch_profile_id != getattr(branch_profile, "id", None):
            raise serializers.ValidationError(
                {"role": "Staff role must belong to the selected branch."}
            )
        if waiter_type and waiter_type.branch_profile_id != getattr(branch_profile, "id", None):
            raise serializers.ValidationError(
                {"waiter_type": "Waiter type must belong to the selected branch."}
            )
        for key, value in list(validated_data.items()):
            if key in {"login_username", "login_password", "login_email"}:
                continue
            setattr(instance, key, value)
        instance.save()
        self._upsert_login_user(instance, validated_data)
        return instance


class EventStaffAssignmentSerializer(serializers.ModelSerializer):
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
        paid_amount = data.get("paid_amount", 0)
        total_days = data.get("total_days", 1)
        per_person_rate = data.get("per_person_rate")

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
            session = data.get("session", getattr(self.instance, "session", None))
            if session and staff.branch_profile_id != session.booking.branch_profile_id:
                raise serializers.ValidationError(
                    {"staff": "Staff and event session must belong to the same branch."}
                )

            if staff.staff_type == "Fixed":
                calc_amount = Decimal("0.00")
            else:
                calc_rate = (
                    per_person_rate
                    if per_person_rate is not None
                    else staff.per_person_rate
                )
                number_of_persons = data.get(
                    "number_of_persons",
                    getattr(self.instance, "number_of_persons", 1),
                )
                calc_amount = calc_rate * total_days * number_of_persons

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
        months_count = data.get(
            "months_count",
            getattr(self.instance, "months_count", Decimal("1.0")),
        )
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
