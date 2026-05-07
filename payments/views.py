from rest_framework.response import Response
from rest_framework import status, generics
from Expense.models import Expense
from eventstaff.models import EventStaffAssignment, FixedStaffSalaryPayment
from django.db.models import Sum, Case, When, F, Value, DecimalField
from radha.Utils.permissions import *
from user.branching import ensure_object_in_user_branch, filter_branch_queryset
from .serializers import *
from datetime import date
from decimal import Decimal


# --------------------    PaymentViewSet    --------------------


class PaymentViewSet(generics.GenericAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "payments"

    def get_queryset(self):
        return filter_branch_queryset(Payment.objects.all(), self.request)

    def get(self, request):
        payments = self.get_queryset().order_by("-payment_date")
        serializer = PaymentSerializer(payments, many=True)
        return Response(
            {
                "status": True,
                "message": "Payment list retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = PaymentSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            data = serializer.validated_data
            booking = data.get("booking")
            if not booking:
                return Response(
                    {"status": False, "message": "booking is required", "data": {}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            ensure_object_in_user_branch(booking, request)

            total_amount = data.get("total_amount", 0)
            total_extra_amount = data.get("total_extra_amount", 0)
            payment_mode = data.get("payment_mode", "OTHER")
            payment_date = data.get("payment_date", date.today())
            note = data.get("note", "")

            # Get the exact transaction amount for this specific request
            if "transaction_amount" in request.data:
                tx_amount = data.get("transaction_amount", 0)
            else:
                tx_amount = data.get("advance_amount", 0)

            # Check if this booking already has a PAID payment
            existing_paid = self.get_queryset().filter(
                booking=booking, payment_status="PAID"
            ).first()
            if existing_paid:
                return Response(
                    {
                        "status": False,
                        "message": "Payment already exists and is fully paid for this booking.",
                        "data": {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check for partial/unpaid payments for THIS booking
            existing_payment = self.get_queryset().filter(
                booking=booking, payment_status__in=["PARTIAL", "UNPAID"]
            ).first()
            if existing_payment:
                # Update the existing payment
                existing_payment.total_amount = total_amount
                existing_payment.total_extra_amount = total_extra_amount

                # Advance is total paid
                existing_payment.advance_amount += tx_amount

                # Settlement on POST: incremental, mirrors PUT semantics so a
                # repeat call with settlement_amount adds to the running total.
                incoming_settlement = data.get("settlement_amount")
                if incoming_settlement not in (None, ""):
                    existing_payment.settlement_amount = (
                        (existing_payment.settlement_amount or Decimal("0"))
                        + Decimal(str(incoming_settlement))
                    )

                # Recalculate pending. Settlement counts toward closing the bill.
                settlement_total = existing_payment.settlement_amount or Decimal("0")
                existing_payment.pending_amount = (
                    existing_payment.total_amount
                    - existing_payment.advance_amount
                    - settlement_total
                )
                if existing_payment.pending_amount < 0:
                    existing_payment.pending_amount = 0

                if existing_payment.pending_amount <= 0:
                    existing_payment.payment_status = "PAID"
                else:
                    existing_payment.payment_status = "PARTIAL"

                existing_payment.save()

                # Record transaction history if advance was paid
                if tx_amount > 0:
                    tx_type = "PARTIAL"
                    if existing_payment.pending_amount <= 0:
                        tx_type = "FINAL"
                    TransactionHistory.objects.create(
                        payment=existing_payment,
                        transaction_date=payment_date,
                        amount=Decimal(str(tx_amount)),
                        payment_mode=payment_mode,
                        transaction_type=tx_type,
                        note=note,
                    )

                return Response(
                    {
                        "status": True,
                        "message": "Payment updated successfully",
                        "data": PaymentSerializer(existing_payment).data,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                # Calculate pending amount for new payment
                pending_amount = total_amount - tx_amount
                if pending_amount < 0:
                    pending_amount = 0
                
                payment_status = "PAID" if pending_amount <= 0 else ("PARTIAL" if tx_amount > 0 else "UNPAID")
                
                payment = serializer.save(
                    branch_profile=booking.branch_profile,
                    advance_amount=tx_amount,
                    pending_amount=pending_amount,
                    payment_status=payment_status
                )

                # Record transaction history if advance was paid on creation
                if tx_amount > 0:
                    TransactionHistory.objects.create(
                        payment=payment,
                        transaction_date=payment_date,
                        amount=Decimal(str(tx_amount)),
                        payment_mode=payment_mode,
                        transaction_type="ADVANCE",
                        note=note,
                    )

                return Response(
                    {
                        "status": True,
                        "message": "Payment created successfully",
                        "data": PaymentSerializer(payment).data,
                    },
                    status=status.HTTP_200_OK,
                )

        return Response(
            {"status": False, "message": "Something went wrong", "data": {}},
            status=status.HTTP_400_BAD_REQUEST,
        )


class EditPaymentViewSet(generics.GenericAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "payments"

    def get_queryset(self):
        return filter_branch_queryset(Payment.objects.all(), self.request)

    def get(self, request, pk=None):
        try:
            payment = self.get_queryset().get(pk=pk)
            serializer = PaymentSerializer(payment)
            return Response(
                {
                    "status": True,
                    "message": "Payment retrieved successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except Payment.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Payment not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

    def put(self, request, pk=None):
        try:
            payment = self.get_queryset().get(pk=pk)
            transaction_amount = request.data.get("transaction_amount")
            settlement_amount = request.data.get("settlement_amount")
            payment_mode = request.data.get("payment_mode", "OTHER")
            payment_date = request.data.get("payment_date", str(date.today()))
            note = request.data.get("note", "")

            # Both transaction and settlement amounts in this request reduce
            # the bill's pending — transaction_amount is cash-style payment
            # (added to cumulative advance), settlement_amount is a write-off
            # (added to cumulative settlement). Both fields on the model are
            # cumulative so we += each new value rather than overwrite.
            tx_amount = Decimal(str(transaction_amount)) if transaction_amount else Decimal("0")
            new_settlement = payment.settlement_amount or Decimal("0")
            if settlement_amount not in (None, ""):
                new_settlement = new_settlement + Decimal(str(settlement_amount))

            if tx_amount > 0 or settlement_amount not in (None, ""):
                new_advance = payment.advance_amount + tx_amount
                new_pending = payment.total_amount - new_advance - new_settlement

                if new_pending < 0:
                    new_pending = Decimal("0")

                request.data["advance_amount"] = str(new_advance)
                request.data["settlement_amount"] = str(new_settlement)
                request.data["pending_amount"] = str(new_pending)

                # Determine transaction-history entry type for this hit.
                if new_pending <= 0:
                    tx_type = "FINAL"
                elif payment.transactions.exists():
                    tx_type = "PARTIAL"
                else:
                    tx_type = "ADVANCE"
            else:
                tx_type = None

            serializer = PaymentSerializer(payment, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
                updated_payment = serializer.save()

                # Auto-update payment_status based on pending. Settlement is
                # part of the equation now — pending = total − advance − settlement.
                settlement = updated_payment.settlement_amount or Decimal("0")
                pending = updated_payment.total_amount - updated_payment.advance_amount - settlement
                if pending < 0:
                    pending = Decimal("0")
                updated_payment.pending_amount = pending

                if pending <= 0:
                    updated_payment.payment_status = "PAID"
                elif updated_payment.advance_amount > 0 or settlement > 0:
                    updated_payment.payment_status = "PARTIAL"
                else:
                    updated_payment.payment_status = "UNPAID"
                updated_payment.save()

                # Record transaction history
                if transaction_amount and tx_type:
                    # Parse payment_date safely
                    from datetime import datetime

                    try:
                        parsed_date = datetime.strptime(payment_date, "%d-%m-%Y").date()
                    except (ValueError, TypeError):
                        parsed_date = date.today()

                    TransactionHistory.objects.create(
                        payment=updated_payment,
                        transaction_date=parsed_date,
                        amount=Decimal(str(transaction_amount)),
                        payment_mode=payment_mode,
                        transaction_type=tx_type,
                        note=note,
                    )

                return Response(
                    {
                        "status": True,
                        "message": "Payment updated successfully",
                        "data": PaymentSerializer(updated_payment).data,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        except Payment.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Payment not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

    def delete(self, request, pk=None):
        try:
            payment = self.get_queryset().get(pk=pk)
            payment.delete()
            return Response(
                {
                    "status": True,
                    "message": "Payment deleted successfully",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        except Payment.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Payment not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )


class AllTransactionViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "transactions"

    def get(self, request):

        payments = filter_branch_queryset(Payment.objects.all(), request)
        expenses = Expense.objects.all()
        expenses = filter_branch_queryset(expenses, request)
        staff_assignments = filter_branch_queryset(
            EventStaffAssignment.objects.all(),
            request,
            field_name="staff__branch_profile",
        )
        fixed_salary_payments = filter_branch_queryset(
            FixedStaffSalaryPayment.objects.all(),
            request,
            field_name="staff__branch_profile",
        )

        if (
            not payments.exists()
            and not expenses.exists()
            and not staff_assignments.exists()
            and not fixed_salary_payments.exists()
        ):
            return Response(
                {
                    "status": False,
                    "message": "No transactions found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

        zero = Value(Decimal("0"), output_field=DecimalField(max_digits=20, decimal_places=2))

        payment_totals = payments.aggregate(
            total_payment_amount=Sum("total_amount"),
            total_paid_amount=Sum(
                Case(
                    When(payment_status="PAID", then=F("total_amount")),
                    When(payment_status__in=["UNPAID", "PARTIAL"], then=F("advance_amount")),
                    default=zero,
                    output_field=DecimalField(max_digits=20, decimal_places=2),
                )
            ),
            total_unpaid_amount=Sum(
                Case(
                    When(payment_status__in=["UNPAID", "PARTIAL"], then=F("pending_amount")),
                    default=zero,
                    output_field=DecimalField(max_digits=20, decimal_places=2),
                )
            ),
            total_settlement_amount=Sum("settlement_amount"),
        )
        total_payment_amount = payment_totals["total_payment_amount"] or Decimal("0")
        total_paid_amount = payment_totals["total_paid_amount"] or Decimal("0")
        total_unpaid_amount = payment_totals["total_unpaid_amount"] or Decimal("0")
        total_settlement_amount = payment_totals["total_settlement_amount"] or Decimal("0")

        direct_expense_total = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        staff_paid_total = (
            staff_assignments.aggregate(total=Sum("paid_amount"))["total"] or Decimal("0")
        )
        fixed_salary_paid_total = (
            fixed_salary_payments.aggregate(total=Sum("paid_amount"))["total"] or Decimal("0")
        )
        total_expense_amount = (
            direct_expense_total + staff_paid_total + fixed_salary_paid_total
        )

        # 🔹 Net Calculation (Payment - Expense)
        net_amount = total_payment_amount - total_expense_amount

        final_response = {
            "net_amount": int(net_amount),
            "total_paid_amount": int(total_paid_amount),
            "total_unpaid_amount": int(total_unpaid_amount),
            "total_settlement_amount": int(total_settlement_amount),
            "total_expense_amount": int(total_expense_amount),
        }

        return Response(
            {
                "status": True,
                "message": "Transaction summary",
                "data": final_response,
            },
            status=status.HTTP_200_OK,
        )
