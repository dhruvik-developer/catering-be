from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from eventbooking.models import EventBooking
from notifications.models import Notification
from notifications.services import NotificationService, iter_admin_recipients
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
        # The ViewSet-level `IsAdminUserOrReadOnly` would block non-admin
        # staff from POSTing — but the whole point of /respond/ is that the
        # **assigned staff member** (who is *not* an admin) accepts or
        # declines. We loosen it to just `IsAuthenticated` here and enforce
        # the real "you can only act on your own row" rule inside the action.
        permission_classes=[IsAuthenticated],
    )
    @transaction.atomic
    def respond(self, request, pk=None):
        """Staff (or an admin acting on their behalf) accepts or declines an
        assignment. Updates the live status fields and writes a row to
        `response_history` so the timeline is preserved across reassignments.

        Body shape:
            { "response": "accepted" | "declined", "reason": "optional text" }
        """
        # Look the assignment up directly — NOT via `self.get_queryset()` which
        # applies `filter_branch_queryset` and returns empty for any user
        # without a `branch_profile_id` (i.e. most regular staff). The
        # authorization model for this action is row-level ("you own this
        # assignment OR you're an admin"), checked just below, so we don't
        # need the branch scope here.
        try:
            assignment = (
                EventStaffAssignment.objects
                .select_related("staff", "staff__user_account")
                .get(pk=pk)
            )
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

        # Alert the catering admins so the response surfaces in their Alerts
        # bell without having to refresh the order page. Errors here must NOT
        # break the staff member's accept/decline flow — wrap in try/except so
        # a notification glitch can't 500 the API.
        try:
            self._notify_admins_of_staff_response(assignment, response_value, reason)
        except Exception:  # noqa: BLE001 — notification is best-effort
            import logging
            logging.getLogger("notifications").exception(
                "Failed to dispatch staff-response admin notification "
                "(assignment=%s)",
                assignment.id,
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

    @staticmethod
    def _notify_admins_of_staff_response(assignment, response_value, reason):
        """Fan a single accept/decline action out to every admin who should
        know. Recipients = main tenant admins + branch admins of the staff
        member's branch (mirrors `iter_admin_recipients`)."""
        staff = assignment.staff
        session = assignment.session
        booking = getattr(session, "booking", None) if session else None
        staff_name = getattr(staff, "name", None) or "A staff member"
        branch_id = getattr(staff, "branch_profile_id", None)

        if response_value == EventStaffAssignment.RESPONSE_ACCEPTED:
            title = "Staff accepted assignment"
            message = (
                f"{staff_name} accepted the assignment for "
                f"{booking.name if booking else 'an event'}."
            )
        else:
            title = "Staff declined assignment"
            base = (
                f"{staff_name} declined the assignment for "
                f"{booking.name if booking else 'an event'}."
            )
            message = f"{base} Reason: {reason}" if reason else base

        data_payload = {
            # Admin deep-link target on the React app.
            "route": f"/view-order-details/{booking.id}" if booking else "",
            "event_id": booking.id if booking else None,
            "session_id": session.id if session else None,
            "assignment_id": assignment.id,
            "response": response_value,
            "reason": reason or "",
            "staff_id": getattr(staff, "id", None),
            "staff_name": staff_name,
        }
        for admin in iter_admin_recipients(branch_id):
            NotificationService.notify_user(
                admin,
                notification_type=Notification.TYPE_STAFF_RESPONSE,
                title=title,
                message=message,
                data=data_payload,
            )

    @action(detail=False, methods=["get"], url_path="event-summary")
    def event_summary(self, request):
        # Declined assignments aren't actually working the event, so they
        # shouldn't inflate the labour/waiter counts or any of the projected
        # amounts. We still want the event itself to appear in the summary
        # (the admin needs to see the row to know to reassign), so the
        # exclusion only applies to the per-field aggregates — not to the
        # `isnull=False` row filter.
        not_declined = ~Q(sessions__staff_assignments__response_status="declined")
        events = (
            filter_branch_queryset(EventBooking.objects, request).annotate(
                total_labor=Count(
                    "sessions__staff_assignments",
                    filter=Q(sessions__staff_assignments__role_at_event__name="Labor")
                    & not_declined,
                ),
                total_waiter=Count(
                    "sessions__staff_assignments",
                    filter=Q(sessions__staff_assignments__role_at_event__name="Waiter")
                    & not_declined,
                ),
                total_amount=Sum(
                    "sessions__staff_assignments__total_amount",
                    filter=not_declined,
                ),
                total_paid=Sum(
                    "sessions__staff_assignments__paid_amount",
                    filter=not_declined,
                ),
                total_pending=Sum(
                    "sessions__staff_assignments__remaining_amount",
                    filter=not_declined,
                ),
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


class MyEventSummaryView(APIView):
    """`GET /api/me/event-summary/`

    Returns the logged-in staff member's own at-a-glance financial summary:
    how many events they're attached to, their projected earnings, what's
    been paid out, what's still owed — plus the most recent assignments so
    they can scan the timeline without leaving the screen.

    Vendor user support is intentionally **not** here yet (vendors are
    settled via Payment / outsourced invoices, not EventStaffAssignment) —
    that's a separate endpoint when we tackle vendor payments.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Find the staff profile linked to this user, if any. Same lookup the
        # rest of the staff-portal endpoints use.
        staff = Staff.objects.filter(user_account=user).first()

        # Only count non-declined assignments — declined work isn't going to
        # be paid out so it shouldn't pollute earnings totals.
        qs = (
            EventStaffAssignment.objects.filter(staff__user_account=user)
            .exclude(response_status=EventStaffAssignment.RESPONSE_DECLINED)
            .select_related(
                "staff",
                "session",
                "session__booking",
                "role_at_event",
                "staff__role",
            )
        )

        totals = qs.aggregate(
            events_worked=Count("id"),
            total_earning=Sum("total_amount"),
            total_paid=Sum("paid_amount"),
            total_pending=Sum("remaining_amount"),
        )

        def _money(value):
            return str(value if value is not None else Decimal("0.00"))

        recent_assignments = []
        for assignment in qs.order_by("-session__event_date")[:20]:
            session = assignment.session
            booking = session.booking if session else None
            role_name = (
                assignment.role_at_event.name
                if assignment.role_at_event
                else (assignment.staff.role.name if assignment.staff.role else "")
            )
            recent_assignments.append(
                {
                    "assignment_id": assignment.id,
                    "booking_id": booking.id if booking else None,
                    "booking_name": booking.name if booking else "",
                    "session_id": session.id if session else None,
                    "session_date": (
                        session.event_date.strftime("%d-%m-%Y")
                        if session and session.event_date
                        else ""
                    ),
                    "session_time": session.event_time if session else "",
                    "role": role_name,
                    "staff_type": assignment.staff.staff_type,
                    "total_amount": _money(assignment.total_amount),
                    "paid_amount": _money(assignment.paid_amount),
                    "remaining_amount": _money(assignment.remaining_amount),
                    "payment_status": assignment.payment_status,
                    "response_status": assignment.response_status,
                }
            )

        # Fixed staff are salaried (their per-assignment total is always 0),
        # so the event-level totals understate what they're actually owed.
        # Fold in their FixedStaffSalaryPayment ledger so they see the real
        # numbers next to the per-event ones.
        #
        # This block mirrors the admin's `staff/<pk>/fixed-payment-summary/`
        # view but trimmed to what the mobile screen renders — joining date,
        # months-equivalent maths, pending withdrawals, and the salary payment
        # records list. We compute the same values inline so the staff portal
        # doesn't need the admin-gated `staff.view_summary` permission.
        fixed_salary_summary = None
        if staff and staff.staff_type == "Fixed":
            salary_payments_qs = FixedStaffSalaryPayment.objects.filter(
                staff=staff
            ).order_by("-start_date", "-created_at")
            salary_totals = salary_payments_qs.aggregate(
                lifetime_total=Sum("total_amount"),
                lifetime_paid=Sum("paid_amount"),
                lifetime_pending=Sum("remaining_amount"),
            )
            lifetime_paid = salary_totals.get("lifetime_paid") or Decimal("0.00")
            monthly_salary = staff.fixed_salary or Decimal("0.00")

            # How many months of salary has actually been paid out, fractional.
            paid_months_equivalent = Decimal("0.00")
            if monthly_salary > 0:
                paid_months_equivalent = (
                    lifetime_paid / monthly_salary
                ).quantize(Decimal("0.01"))

            # Whole-month tenure since joining; subtract 1 if today is before
            # the joining-day-of-month so partial months don't get counted as
            # "owed" prematurely. Matches the admin view's calc.
            tenure_months = 0
            if staff.joining_date:
                today = timezone.now().date()
                tenure_months = (today.year - staff.joining_date.year) * 12 + (
                    today.month - staff.joining_date.month
                )
                if today.day < staff.joining_date.day:
                    tenure_months -= 1
                if tenure_months < 0:
                    tenure_months = 0

            pending_withdrawals = (
                staff.withdrawals.filter(is_adjusted=False).aggregate(
                    total=Sum("amount")
                )["total"]
                or Decimal("0.00")
            )

            salary_payment_records = [
                {
                    "id": p.id,
                    "period_label": p.covered_month_label,
                    "start_date": (
                        p.start_date.strftime("%d-%m-%Y") if p.start_date else ""
                    ),
                    "end_date": (
                        p.end_date.strftime("%d-%m-%Y") if p.end_date else ""
                    ),
                    "months_count": str(p.months_count or 0),
                    "total_amount": _money(p.total_amount),
                    "paid_amount": _money(p.paid_amount),
                    "remaining_amount": _money(p.remaining_amount),
                    "withdrawal_deduction": _money(p.withdrawal_deduction),
                    "payment_status": p.payment_status,
                    "payment_date": (
                        p.payment_date.strftime("%d-%m-%Y")
                        if p.payment_date
                        else ""
                    ),
                }
                for p in salary_payments_qs
            ]

            fixed_salary_summary = {
                "monthly_salary": _money(monthly_salary),
                "lifetime_total": _money(salary_totals.get("lifetime_total")),
                "lifetime_paid": _money(lifetime_paid),
                "lifetime_pending": _money(salary_totals.get("lifetime_pending")),
                "joining_date": (
                    staff.joining_date.strftime("%Y-%m-%d")
                    if staff.joining_date
                    else None
                ),
                "tenure_months": tenure_months,
                "paid_months_equivalent": str(paid_months_equivalent),
                # Pending months = months elapsed minus what's been paid for —
                # never negative (e.g. if admin paid forward).
                "pending_months": str(
                    max(
                        Decimal(str(tenure_months)) - paid_months_equivalent,
                        Decimal("0.00"),
                    ).quantize(Decimal("0.01"))
                ),
                "pending_withdrawals": _money(pending_withdrawals),
                "salary_payment_records": salary_payment_records,
            }

        return Response(
            {
                "status": True,
                "message": "Summary fetched.",
                "data": {
                    "user_type": "staff" if staff else "unknown",
                    "staff_name": (
                        staff.name
                        if staff
                        else (user.get_full_name() or user.username)
                    ),
                    "staff_type": staff.staff_type if staff else None,
                    "totals": {
                        "events_worked": totals.get("events_worked") or 0,
                        "total_earning": _money(totals.get("total_earning")),
                        "total_paid": _money(totals.get("total_paid")),
                        "total_pending": _money(totals.get("total_pending")),
                    },
                    "recent_assignments": recent_assignments,
                    "fixed_salary_summary": fixed_salary_summary,
                },
            },
            status=status.HTTP_200_OK,
        )
