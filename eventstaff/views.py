from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from eventbooking.models import EventBooking
from radha.Utils.permissions import IsAdminUserOrReadOnly
from user.branching import (
    ensure_object_in_user_branch,
    filter_branch_queryset,
    get_branch_save_kwargs,
)

from .models import (
    EventStaffAssignment,
    EventStaffAssignmentResponse,
    FixedStaffSalaryPayment,
    Staff,
    StaffRole,
    StaffWithdrawal,
    WaiterType,
)
from .serializers import (
    EventStaffAssignmentSerializer,
    FixedStaffSalaryPaymentSerializer,
    StaffRoleSerializer,
    StaffSerializer,
    StaffWithdrawalSerializer,
    WaiterTypeSerializer,
)


def decimal_to_string(value):
    return str(value if value is not None else Decimal("0.00"))


class StaffRoleViewSet(viewsets.ModelViewSet):
    queryset = StaffRole.objects.all().order_by("name")
    serializer_class = StaffRoleSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "staff_roles"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        return filter_branch_queryset(super().get_queryset(), self.request)

    def perform_create(self, serializer):
        serializer.save(**get_branch_save_kwargs(self.request))


class WaiterTypeViewSet(viewsets.ModelViewSet):
    queryset = WaiterType.objects.all().order_by("name")
    serializer_class = WaiterTypeSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "waiter_types"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "per_person_rate"]

    def get_queryset(self):
        return filter_branch_queryset(super().get_queryset(), self.request)

    def perform_create(self, serializer):
        serializer.save(**get_branch_save_kwargs(self.request))


class StaffViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.select_related("role", "waiter_type", "user_account").all().order_by(
        "-created_at"
    )
    serializer_class = StaffSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "staff"
    permission_action_map = {
        "waiters": "staff.view",
        "fixed_payment_summary": "staff.view_summary",
    }
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["role", "staff_type", "is_active"]
    search_fields = ["name", "phone", "user_account__username"]
    ordering_fields = ["name", "created_at", "per_person_rate"]

    def get_queryset(self):
        return filter_branch_queryset(super().get_queryset(), self.request)

    def create(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.is_staff):
            raise PermissionDenied("Only admin can create this resource.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(**get_branch_save_kwargs(self.request))

    @action(detail=False, methods=["get"], url_path="waiters")
    def waiters(self, request):
        role_name = request.query_params.get("role", "Waiter")
        waiter_type_name = request.query_params.get("waiter_type")

        query_filters = {"role__name__iexact": role_name}
        if waiter_type_name:
            query_filters["waiter_type__name__iexact"] = waiter_type_name

        waiters = (
            filter_branch_queryset(Staff.objects.filter(**query_filters), request)
            .values(
                "id",
                "name",
                "phone",
                "staff_type",
                "fixed_salary",
                "per_person_rate",
                "agency_services",
                "is_active",
                "role__name",
                "waiter_type__name",
                "waiter_type__per_person_rate",
                "user_account__username",
            )
            .order_by("name")
        )

        result = []
        for waiter in waiters:
            result.append(
                {
                    "id": waiter["id"],
                    "name": waiter["name"],
                    "phone": waiter["phone"],
                    "staff_type": waiter["staff_type"],
                    "role": waiter["role__name"],
                    "waiter_type": waiter.get("waiter_type__name"),
                    "waiter_type_rate": float(
                        waiter.get("waiter_type__per_person_rate") or 0.0
                    ),
                    "per_person_rate": float(waiter["per_person_rate"] or 0.0),
                    "agency_services": waiter.get("agency_services") or [],
                    "fixed_salary": float(waiter["fixed_salary"] or 0.0),
                    "is_active": waiter["is_active"],
                    "linked_username": waiter.get("user_account__username"),
                }
            )

        return Response(
            {
                "status": True,
                "message": f"{role_name} list fetched successfully",
                "data": result,
            }
        )

    @action(detail=True, methods=["get"], url_path="fixed-payment-summary")
    def fixed_payment_summary(self, request, pk=None):
        staff = self.get_object()

        if staff.staff_type != "Fixed":
            return Response(
                {
                    "status": False,
                    "message": "This summary is only available for Fixed staff.",
                    "data": {},
                },
                status=400,
            )

        salary_payments = staff.salary_payments.all().order_by("-start_date", "-created_at")
        event_assignments = (
            staff.event_assignments.select_related(
                "session", "session__booking", "role_at_event"
            )
            .all()
            .order_by("-created_at")
        )

        salary_totals = salary_payments.aggregate(
            total_salary_amount=Sum("total_amount"),
            total_salary_paid=Sum("paid_amount"),
            total_salary_pending=Sum("remaining_amount"),
            total_salary_months=Sum("months_count"),
        )
        total_salary_amount = salary_totals["total_salary_amount"] or Decimal("0.00")
        total_salary_paid = salary_totals["total_salary_paid"] or Decimal("0.00")
        total_salary_pending = salary_totals["total_salary_pending"] or Decimal("0.00")
        total_salary_months = salary_totals["total_salary_months"] or 0

        total_event_paid = (
            event_assignments.aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0.00")
        )

        fixed_salary = staff.fixed_salary or Decimal("0.00")
        paid_months_equivalent = Decimal("0.00")
        if fixed_salary > 0:
            paid_months_equivalent = (total_salary_paid / fixed_salary).quantize(
                Decimal("0.01")
            )

        import django.utils.timezone

        months_passed = 0
        if staff.joining_date:
            today = django.utils.timezone.now().date()
            years_diff = today.year - staff.joining_date.year
            months_diff = today.month - staff.joining_date.month
            months_passed = years_diff * 12 + months_diff

            if today.day < staff.joining_date.day:
                months_passed -= 1

            if months_passed < 0:
                months_passed = 0

        pending_withdrawals = staff.withdrawals.filter(is_adjusted=False)
        total_pending_withdrawals = (
            pending_withdrawals.aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        last_payment = salary_payments.first()
        last_payment_end_date = (
            last_payment.end_date.strftime("%Y-%m-%d") if last_payment else None
        )

        final_response = {
            "staff_id": staff.id,
            "staff_name": staff.name,
            "staff_type": staff.staff_type,
            "role_name": staff.role.name if staff.role else None,
            "linked_username": (
                staff.user_account.username if staff.user_account else None
            ),
            "joining_date": (
                staff.joining_date.strftime("%Y-%m-%d") if staff.joining_date else None
            ),
            "months_passed": months_passed,
            "pending_months": decimal_to_string(
                Decimal(str(months_passed)) - paid_months_equivalent
            ),
            "total_pending_withdrawals": decimal_to_string(total_pending_withdrawals),
            "last_payment_end_date": last_payment_end_date,
            "fixed_salary": decimal_to_string(fixed_salary),
            "total_salary_records": salary_payments.count(),
            "total_salary_months": total_salary_months,
            "paid_months_equivalent": decimal_to_string(paid_months_equivalent),
            "total_salary_amount": decimal_to_string(total_salary_amount),
            "total_salary_paid": decimal_to_string(total_salary_paid),
            "total_salary_pending": decimal_to_string(total_salary_pending),
            "total_event_records": event_assignments.count(),
            "total_event_paid": decimal_to_string(total_event_paid),
            "total_overall_paid": decimal_to_string(
                total_salary_paid + total_event_paid
            ),
            "salary_payments": FixedStaffSalaryPaymentSerializer(
                salary_payments,
                many=True,
            ).data,
            "event_payments": EventStaffAssignmentSerializer(
                event_assignments,
                many=True,
            ).data,
        }

        return Response(
            {
                "status": True,
                "message": "Fixed staff payment summary fetched successfully",
                "data": final_response,
            }
        )


class FixedStaffSalaryPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = FixedStaffSalaryPaymentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "fixed_staff_payments"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["staff", "payment_status"]
    search_fields = ["staff__name", "note"]
    ordering_fields = ["start_date", "end_date", "payment_date", "paid_amount", "created_at"]

    def get_queryset(self):
        qs = (
            FixedStaffSalaryPayment.objects.select_related("staff", "staff__role")
            .all()
            .order_by("-start_date", "-created_at")
        )
        qs = filter_branch_queryset(qs, self.request, field_name="staff__branch_profile")

        staff_id = self.request.query_params.get("staff")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)

        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(start_date__year=year)

        month = self.request.query_params.get("month")
        if month:
            qs = qs.filter(start_date__month=month)

        return qs

    def perform_create(self, serializer):
        staff = serializer.validated_data["staff"]
        ensure_object_in_user_branch(staff, self.request)
        months_count = serializer.validated_data["months_count"]
        fixed_salary = staff.fixed_salary or Decimal("0.00")
        gross_amount = fixed_salary * Decimal(str(months_count))

        pending_withdrawals = staff.withdrawals.filter(is_adjusted=False).order_by(
            "created_at"
        )
        total_withdrawal_amount = (
            pending_withdrawals.aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        withdrawal_deduction = min(total_withdrawal_amount, gross_amount)
        payment = serializer.save(withdrawal_deduction=withdrawal_deduction)

        remaining_deduction_budget = withdrawal_deduction
        for withdrawal in pending_withdrawals:
            if remaining_deduction_budget >= withdrawal.amount:
                withdrawal.is_adjusted = True
                withdrawal.adjusted_in_payment = payment
                withdrawal.save()
                remaining_deduction_budget -= withdrawal.amount
            elif remaining_deduction_budget > 0:
                excess = withdrawal.amount - remaining_deduction_budget
                withdrawal.amount = remaining_deduction_budget
                withdrawal.is_adjusted = True
                withdrawal.adjusted_in_payment = payment
                withdrawal.save()

                StaffWithdrawal.objects.create(
                    staff=staff,
                    amount=excess,
                    payment_date=payment.payment_date or withdrawal.payment_date,
                    note="Remainder from partial adjustment of previous advance.",
                    is_adjusted=False,
                )
                break


class StaffWithdrawalViewSet(viewsets.ModelViewSet):
    queryset = StaffWithdrawal.objects.all().order_by("-payment_date", "-created_at")
    serializer_class = StaffWithdrawalSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "staff_withdrawals"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["staff", "is_adjusted"]
    search_fields = ["staff__name", "note"]
    ordering_fields = ["payment_date", "amount", "created_at"]

    def get_queryset(self):
        qs = filter_branch_queryset(
            super().get_queryset(),
            self.request,
            field_name="staff__branch_profile",
        )
        staff_id = self.request.query_params.get("staff")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        return qs


class EventStaffAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = EventStaffAssignmentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_staff_assignments"
    permission_action_map = {
        "event_summary": "event_staff_assignments.view_summary",
    }
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "session",
        "payment_status",
        "staff__staff_type",
    ]
    search_fields = ["staff__name", "session__booking__name"]
    ordering_fields = ["created_at", "total_amount", "paid_amount"]

    def get_queryset(self):
        qs = (
            EventStaffAssignment.objects.select_related(
                "staff", "session", "session__booking"
            )
            .all()
            .order_by("-created_at")
        )
        qs = filter_branch_queryset(qs, self.request, field_name="staff__branch_profile")

        staff_type = self.request.query_params.get("staff_type")
        if staff_type:
            qs = qs.filter(staff__staff_type=staff_type)

        return qs

    @action(
        detail=True,
        methods=["post"],
        url_path="respond",
        # Anyone authenticated can call this; we enforce that only the
        # assigned staff (or an admin) can act on the row inside the body of
        # the action.
        permission_classes=[IsAdminUserOrReadOnly],
    )
    @transaction.atomic
    def respond(self, request, pk=None):
        """Staff (or an admin acting on their behalf) accepts or declines an
        assignment. Updates the live status fields and writes a row to
        `response_history` so the timeline is preserved across reassignments.

        Body shape:
            { "response": "accepted" | "declined", "reason": "optional text" }
        """
        try:
            assignment = self.get_queryset().get(pk=pk)
        except EventStaffAssignment.DoesNotExist:
            return Response(
                {"status": False, "message": "Assignment not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Authorization: the assignment's staff.user_account must match the
        # caller, OR the caller must be an admin. We check explicitly instead
        # of relying on a permission class because the rule is row-specific.
        user = request.user
        staff_user_id = getattr(assignment.staff, "user_account_id", None)
        is_owner = bool(staff_user_id) and staff_user_id == user.id
        is_admin = bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
        if not (is_owner or is_admin):
            raise PermissionDenied(
                "You can only respond to assignments that belong to you."
            )

        response_value = str(request.data.get("response", "")).strip().lower()
        if response_value not in (
            EventStaffAssignment.RESPONSE_ACCEPTED,
            EventStaffAssignment.RESPONSE_DECLINED,
        ):
            return Response(
                {
                    "status": False,
                    "message": "`response` must be 'accepted' or 'declined'.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = str(request.data.get("reason", "") or "").strip()
        if response_value == EventStaffAssignment.RESPONSE_DECLINED and not reason:
            return Response(
                {
                    "status": False,
                    "message": "A reason is required when declining an assignment.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        assignment.response_status = response_value
        assignment.decline_reason = (
            reason if response_value == EventStaffAssignment.RESPONSE_DECLINED else ""
        )
        assignment.responded_at = now
        assignment.save(
            update_fields=["response_status", "decline_reason", "responded_at", "updated_at"]
        )

        EventStaffAssignmentResponse.objects.create(
            assignment=assignment,
            response=response_value,
            reason=reason,
            responded_by=user,
            responded_at=now,
        )

        serializer = self.get_serializer(assignment)
        return Response(
            {
                "status": True,
                "message": (
                    "Assignment accepted."
                    if response_value == EventStaffAssignment.RESPONSE_ACCEPTED
                    else "Assignment declined."
                ),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="event-summary")
    def event_summary(self, request):
        events = (
            filter_branch_queryset(EventBooking.objects, request).annotate(
                total_labor=Count(
                    "sessions__staff_assignments",
                    filter=Q(sessions__staff_assignments__role_at_event__name="Labor"),
                ),
                total_waiter=Count(
                    "sessions__staff_assignments",
                    filter=Q(sessions__staff_assignments__role_at_event__name="Waiter"),
                ),
                total_amount=Sum("sessions__staff_assignments__total_amount"),
                total_paid=Sum("sessions__staff_assignments__paid_amount"),
                total_pending=Sum("sessions__staff_assignments__remaining_amount"),
            )
            .filter(sessions__staff_assignments__isnull=False)
            .distinct()
            .order_by("-date")
        )

        page = self.paginate_queryset(events)
        data = []
        iterable = page if page is not None else events

        for event in iterable:
            data.append(
                {
                    "event_id": event.id,
                    "event_name": event.name,
                    "event_date": event.date,
                    "total_labor": event.total_labor,
                    "total_waiter": event.total_waiter,
                    "total_amount": (
                        float(event.total_amount) if event.total_amount else 0.0
                    ),
                    "total_paid": float(event.total_paid) if event.total_paid else 0.0,
                    "total_pending": (
                        float(event.total_pending) if event.total_pending else 0.0
                    ),
                }
            )

        if page is not None:
            return self.get_paginated_response(data)

        return Response(
            {
                "status": True,
                "message": "Event staff summary fetched successfully",
                "data": data,
            }
        )
