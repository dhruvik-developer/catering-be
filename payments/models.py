from django.db import models


class Payment(models.Model):
    PAYMENT_MODE_CHOICES = [
        ("CASH", "CASH"),
        ("CHEQUE", "CHEQUE"),
        ("BANK_TRANSFER", "BANK TRANSFER"),
        ("ONLINE", "ONLINE"),
        ("OTHER", "OTHER"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("PARTIAL", "Partial"),
        ("UNPAID", "Unpaid"),
        ("PAID", "Paid"),
    ]

    bill_no = models.AutoField(primary_key=True)
    # Link to a single EventBooking containing multiple sessions
    booking = models.ForeignKey(
        "eventbooking.EventBooking",
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
    )
    total_amount = models.DecimalField(max_digits=100, decimal_places=0)
    total_extra_amount = models.DecimalField(max_digits=250, decimal_places=0)
    advance_amount = models.DecimalField(max_digits=100, decimal_places=0)
    pending_amount = models.DecimalField(
        max_digits=100, decimal_places=0, null=True, blank=True
    )
    payment_date = models.DateField()
    transaction_amount = models.DecimalField(max_digits=100, decimal_places=0)
    payment_mode = models.CharField(
        max_length=200, choices=PAYMENT_MODE_CHOICES, default="OTHER"
    )
    settlement_amount = models.DecimalField(
        max_digits=100, decimal_places=0, null=True, blank=True
    )
    payment_status = models.CharField(
        max_length=100, choices=PAYMENT_STATUS_CHOICES, default="UNPAID"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rule = models.BooleanField(default=False)

    def __str__(self):
        return f"Payment {self.bill_no}"

    @property
    def formatted_event_date(self):
        return self.payment_date.strftime("%d-%m-%Y")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class TransactionHistory(models.Model):
    PAYMENT_MODE_CHOICES = [
        ("CASH", "CASH"),
        ("CHEQUE", "CHEQUE"),
        ("BANK_TRANSFER", "BANK TRANSFER"),
        ("ONLINE", "ONLINE"),
        ("OTHER", "OTHER"),
    ]

    TRANSACTION_TYPE_CHOICES = [
        ("ADVANCE", "Advance"),
        ("PARTIAL", "Partial"),
        ("FINAL", "Final"),
        ("OTHER", "Other"),
    ]

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=100, decimal_places=2)
    payment_mode = models.CharField(
        max_length=200, choices=PAYMENT_MODE_CHOICES, default="OTHER"
    )
    transaction_type = models.CharField(
        max_length=100, choices=TRANSACTION_TYPE_CHOICES, default="OTHER"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction {self.id} for Payment {self.payment.bill_no}"
