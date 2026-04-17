from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


gst_validator = RegexValidator(
    regex=r"^[0-9]{2}[A-Z0-9]{13}$",
    message="GST number must be 15 characters, start with 2 digits, and contain only letters and numbers.",
)


class BranchFormat(models.Model):
    branch_name = models.CharField(max_length=255)
    branch_code = models.CharField(
        max_length=20, unique=True, blank=True, editable=False
    )
    address = models.TextField()
    gst_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[gst_validator],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "branch_format"
        ordering = ["branch_name", "id"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.branch_code:
            return f"{self.branch_name} ({self.branch_code})"
        return self.branch_name

    def save(self, *args, **kwargs):
        if self.branch_name:
            self.branch_name = self.branch_name.strip()
        if self.gst_number:
            self.gst_number = self.gst_number.strip().upper()

        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and not self.branch_code:
            generated_code = f"BR{1000 + self.pk}"
            type(self).objects.filter(pk=self.pk).update(branch_code=generated_code)
            self.branch_code = generated_code


class BranchBankDetails(models.Model):
    branch = models.OneToOneField(
        BranchFormat,
        on_delete=models.CASCADE,
        related_name="bank_details",
    )
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "branch_bank_details"

    def __str__(self):
        return f"{self.branch.display_name} - {self.bank_name}"

    def save(self, *args, **kwargs):
        if self.bank_name:
            self.bank_name = self.bank_name.strip()
        if self.account_number:
            self.account_number = self.account_number.strip()
        if self.ifsc_code:
            self.ifsc_code = self.ifsc_code.strip().upper()
        if self.account_holder_name:
            self.account_holder_name = self.account_holder_name.strip()
        super().save(*args, **kwargs)


class PartyInformation(models.Model):
    party_name = models.CharField(max_length=255)
    party_gst_no = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[gst_validator],
    )
    party_code = models.CharField(max_length=30, unique=True, blank=True)
    invoice_prefix = models.CharField(max_length=30, unique=True, blank=True, null=True)
    next_sequence_no = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "party_information"
        ordering = ["party_name", "id"]

    def __str__(self):
        return self.party_name

    def save(self, *args, **kwargs):
        if self.party_name:
            self.party_name = self.party_name.strip()
        if self.party_gst_no:
            self.party_gst_no = self.party_gst_no.strip().upper()
        if self.party_code:
            self.party_code = self.party_code.strip().upper()
        if self.invoice_prefix:
            self.invoice_prefix = self.invoice_prefix.strip().upper()

        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and not self.party_code:
            generated_code = str(1000 + self.pk)
            type(self).objects.filter(pk=self.pk).update(party_code=generated_code)
            self.party_code = generated_code

    @property
    def next_invoice_preview(self):
        if not self.invoice_prefix:
            return ""
        return f"{self.invoice_prefix}{self.next_sequence_no}"


class GlobalConfiguration(models.Model):
    default_hsn_code = models.CharField(max_length=10, default="996331")

    available_gst_percentages = models.CharField(max_length=50, default="0,5,12,18,28")

    default_gst_percentage = models.IntegerField(default=5)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_gst_list(self):
        return [int(x.strip()) for x in self.available_gst_percentages.split(",")]

    def __str__(self):
        return f"Global Config ({self.id})"


class BranchItem(models.Model):
    branch = models.ForeignKey(
        BranchFormat, on_delete=models.CASCADE, related_name="branch_items"
    )
    name = models.CharField(max_length=255)
    rate = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "branch_item"
        ordering = ["name"]
        unique_together = ("branch", "name")

    def __str__(self):
        return f"{self.name} ({self.branch.branch_name})"


class BranchBill(models.Model):
    branch = models.ForeignKey(
        BranchFormat, on_delete=models.CASCADE, related_name="bills"
    )
    party = models.ForeignKey(
        PartyInformation, on_delete=models.CASCADE, related_name="branch_bills"
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField()
    order_number = models.CharField(max_length=50, blank=True, null=True)
    order_date = models.DateField()
    hsn_code = models.CharField(max_length=10, blank=True, null=True)
    refrance = models.TextField(blank=True, null=True)
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    output_sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    output_cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    round_off = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    final_payable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "branch_bill"
        ordering = ["-invoice_date", "-id"]

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if self.invoice_number:
            self.invoice_number = self.invoice_number.strip().upper()
        if self.order_number:
            self.order_number = self.order_number.strip()
        if self.hsn_code:
            self.hsn_code = self.hsn_code.strip().upper()
        if self.refrance:
            self.refrance = self.refrance.strip()
        if self.notes:
            self.notes = self.notes.strip()
        super().save(*args, **kwargs)


class BranchBillItem(models.Model):
    bill = models.ForeignKey(
        BranchBill, on_delete=models.CASCADE, related_name="items"
    )
    branch_item = models.ForeignKey(
        BranchItem, on_delete=models.PROTECT, related_name="bill_items"
    )
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    rate = models.DecimalField(max_digits=15, decimal_places=2)
    is_rate_inclusive = models.BooleanField(default=False)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "branch_bill_item"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.bill.invoice_number} - {self.item_name}"
