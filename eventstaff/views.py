from decimal import Decimal

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q
from .models import (
    EventStaffAssignment,
    FixedStaffSalaryPayment,
    Staff,
    StaffRole,
    WaiterType,
    StaffWithdrawal,
)
from .serializers import (
    EventStaffAssignmentSerializer,
    FixedStaffSalaryPaymentSerializer,
    StaffSerializer,
    StaffRoleSerializer,
    WaiterTypeSerializer,
    StaffWithdrawalSerializer,
)
from eventbooking.models import EventBooking
from radha.Utils.permissions import IsAdminUserOrReadOnly


def decimal_to_string(value):
    return str(value if value is not None else Decimal("0.00"))


class StaffRoleViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Staff Roles (e.g. Waiter, Manager, Chef)
    """

    queryset = StaffRole.objects.all().order_by("name")
    serializer_class = StaffRoleSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class WaiterTypeViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Waiter Types (VIP, VVIP, Normal, Special Couple, etc.)
    """

    queryset = WaiterType.objects.all().order_by("name")
    serializer_class = WaiterTypeSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "per_person_rate"]


class StaffViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Staff
    """

    queryset = Staff.objects.all().order_by("-created_at")
    serializer_class = StaffSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["role", "staff_type", "is_active"]
    search_fields = ["name", "phone"]
    ordering_fields = ["name", "created_at", "per_person_rate"]

    @action(detail=False, methods=["get"], url_path="waiters")
    def waiters(self, request):
        """Return waiters (role=Waiter) with per-person rates and types."""
        role_name = request.query_params.get("role", "Waiter")
        waiter_type_name = request.query_params.get("waiter_type")

        filters = {"role__name__iexact": role_name}
        if waiter_type_name:
            filters["waiter_type__name__iexact"] = waiter_type_name

        waiters = (
            Staff.objects.filter(**filters)
            .values(
                "id",
                "name",
                "phone",
                "staff_type",
                "fixed_salary",
                "per_person_rate",
                "is_active",
                "role__name",
                "waiter_type__name",
                "waiter_type__per_person_rate",
            )
            .order_by("name")
        )

        result = []
        for w in waiters:
            result.append(
                {
                    "id": w["id"],
                    "name": w["name"],
                    "phone": w["phone"],
                    "staff_type": w["staff_type"],
                    "role": w["role__name"],
                    "waiter_type": w.get("waiter_type__name"),
                    "waiter_type_rate": float(w.get("waiter_type__per_person_rate") or 0.0),
                    "per_person_rate": float(w["per_person_rate"] or 0.0),
                    "fixed_salary": float(w["fixed_salary"] or 0.0),
                    "is_active": w["is_active"],
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
            
            # Calculate full calendar months difference
            years_diff = today.year - staff.joining_date.year
            months_diff = today.month - staff.joining_date.month
            
            months_passed = years_diff * 12 + months_diff
            
            # If today's day of month is earlier than joining date's day of month, 
            # subtract 1 to only count fully passed months (acts like relativedelta)
            if today.day < staff.joining_date.day:
                months_passed -= 1
                
            # Fallback to 0 if negative
            if months_passed < 0:
                months_passed = 0
            
        # Calculate Pending Withdrawals
        pending_withdrawals = staff.withdrawals.filter(is_adjusted=False)
        total_pending_withdrawals = pending_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # Get last payment end date
        last_payment = salary_payments.first() # It's ordered by -start_date
        last_payment_end_date = last_payment.end_date.strftime("%Y-%m-%d") if last_payment else None
            
        final_response = {
            "staff_id": staff.id,
            "staff_name": staff.name,
            "staff_type": staff.staff_type,
            "role_name": staff.role.name if staff.role else None,
            "joining_date": staff.joining_date.strftime("%Y-%m-%d") if staff.joining_date else None,
            "months_passed": months_passed,
            "pending_months": decimal_to_string(Decimal(str(months_passed)) - paid_months_equivalent),
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
    """
    CRUD API for fixed staff monthly salary payments
    """

    serializer_class = FixedStaffSalaryPaymentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
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
        months_count = serializer.validated_data["months_count"]
        fixed_salary = staff.fixed_salary or Decimal("0.00")
        gross_amount = fixed_salary * Decimal(str(months_count))
        
        # Deduct withdrawals
        pending_withdrawals = staff.withdrawals.filter(is_adjusted=False).order_by("created_at")
        total_withdrawal_amount = pending_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        # Simple Logic: Deduct the pending total from standard gross. 
        # (Assuming the frontend form enforces paid_amount = gross - pending_withdrawals)
        # If total_withdrawal_amount > gross_amount, the frontend handles preventing payment 
        # or we just mark them adjusted right now. 
        
        withdrawal_deduction = min(total_withdrawal_amount, gross_amount)
        
        payment = serializer.save(withdrawal_deduction=withdrawal_deduction)
        
        # Mark used withdrawals as adjusted. If partial, we just mark oldest ones fully adjusted until budget runs out
        remaining_deduction_budget = withdrawal_deduction
        for w in pending_withdrawals:
            if remaining_deduction_budget >= w.amount:
                w.is_adjusted = True
                w.adjusted_in_payment = payment
                w.save()
                remaining_deduction_budget -= w.amount
            elif remaining_deduction_budget > 0:
                # Partially adjusting a withdrawal involves making a new unadjusted one out of the excess
                excess = w.amount - remaining_deduction_budget
                w.amount = remaining_deduction_budget
                w.is_adjusted = True
                w.adjusted_in_payment = payment
                w.save()
                
                # create explicit leftover
                StaffWithdrawal.objects.create(
                    staff=staff,
                    amount=excess,
                    payment_date=payment.payment_date or w.payment_date,
                    note=f"Remainder from partial adjustment of previous advance.",
                    is_adjusted=False
                )
                remaining_deduction_budget = Decimal("0.00")
                break


class StaffWithdrawalViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Staff Withdrawals (Advances)
    """

    queryset = StaffWithdrawal.objects.all().order_by("-payment_date", "-created_at")
    serializer_class = StaffWithdrawalSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["staff", "is_adjusted"]
    search_fields = ["staff__name", "note"]
    ordering_fields = ["payment_date", "amount", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        staff_id = self.request.query_params.get("staff")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        return qs


class EventStaffAssignmentViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Event Staff Assignments

    Supports filtering by:
      ?staff_type=Agency|Fixed|Contract   (shorthand for staff__staff_type)
      ?session=<id>
      ?payment_status=Pending|Partial|Paid
    """

    serializer_class = EventStaffAssignmentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
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

        # Allow ?staff_type=Agency  (friendlier alias for staff__staff_type)
        staff_type = self.request.query_params.get("staff_type")
        if staff_type:
            qs = qs.filter(staff__staff_type=staff_type)

        return qs

    @action(detail=False, methods=["get"], url_path="event-summary")
    def event_summary(self, request):
        """
        Return event-wise summary: total labor count, total waiter count, total payment, total paid, total pending
        """
        events = (
            EventBooking.objects.annotate(
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
