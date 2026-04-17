from rest_framework.response import Response
from rest_framework import status, generics
from Expense.models import Expense
from eventstaff.models import EventStaffAssignment, FixedStaffSalaryPayment
from django.db.models import Sum
from radha.Utils.permissions import *
from .serializers import *
from datetime import date


# --------------------    PaymentViewSet    --------------------


class PaymentViewSet(generics.GenericAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get(self, request):
        payments = Payment.objects.all().order_by("-payment_date")
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
            existing_paid = Payment.objects.filter(
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
            existing_payment = Payment.objects.filter(
                booking=booking, payment_status__in=["PARTIAL", "UNPAID"]
            ).first()
            if existing_payment:
                # Update the existing payment
                existing_payment.total_amount = total_amount
                existing_payment.total_extra_amount = total_extra_amount
                
                # Advance is total paid
                existing_payment.advance_amount += tx_amount
                
                # Recalculate pending
                existing_payment.pending_amount = (
                    existing_payment.total_amount - existing_payment.advance_amount
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
                    from decimal import Decimal
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
                    advance_amount=tx_amount,
                    pending_amount=pending_amount,
                    payment_status=payment_status
                )

                # Record transaction history if advance was paid on creation
                if tx_amount > 0:
                    from decimal import Decimal
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

    def get(self, request, pk=None):
        try:
            payment = Payment.objects.get(pk=pk)
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
            payment = Payment.objects.get(pk=pk)
            transaction_amount = request.data.get("transaction_amount")
            payment_mode = request.data.get("payment_mode", "OTHER")
            payment_date = request.data.get("payment_date", str(date.today()))
            note = request.data.get("note", "")

            if transaction_amount:
                from decimal import Decimal

                tx_amount = Decimal(str(transaction_amount))
                new_advance = payment.advance_amount + tx_amount
                new_pending = payment.total_amount - new_advance
                
                if new_pending < 0:
                    new_pending = Decimal("0")

                request.data["advance_amount"] = str(new_advance)
                request.data["pending_amount"] = str(new_pending)

                # Determine transaction type
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

                # Auto-update payment_status based on pending
                from decimal import Decimal

                pending = updated_payment.total_amount - updated_payment.advance_amount
                if pending < 0:
                    pending = Decimal("0")
                updated_payment.pending_amount = pending
                
                if pending <= 0:
                    updated_payment.payment_status = "PAID"
                elif updated_payment.advance_amount > 0:
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
            payment = Payment.objects.get(pk=pk)
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

    def get(self, request):

        payments = Payment.objects.all()
        expenses = Expense.objects.all()
        staff_assignments = EventStaffAssignment.objects.all()
        fixed_salary_payments = FixedStaffSalaryPayment.objects.all()

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

        # 🔹 Payment Aggregation
        total_payment_amount = (
            payments.aggregate(total=Sum("total_amount"))["total"] or 0
        )

        total_paid_amount = 0
        total_unpaid_amount = 0
        total_settlement_amount = 0

        for payment in payments:
            if payment.payment_status == "PAID":
                total_paid_amount += payment.total_amount
            elif payment.payment_status in ["UNPAID", "PARTIAL"]:
                total_unpaid_amount += payment.pending_amount
                total_paid_amount += payment.advance_amount

            total_settlement_amount += payment.settlement_amount or 0

        # 🔹 Expense Aggregation
        direct_expense_total = expenses.aggregate(total=Sum("amount"))["total"] or 0
        staff_paid_total = (
            staff_assignments.aggregate(total=Sum("paid_amount"))["total"] or 0
        )
        fixed_salary_paid_total = (
            fixed_salary_payments.aggregate(total=Sum("paid_amount"))["total"] or 0
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
