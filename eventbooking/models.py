from django.conf import settings
from django.db import models
from django.utils import timezone
from vendor.models import Vendor
from ListOfIngridients.models import IngridientsItem


class EventBooking(models.Model):
    ADVANCE_PAYMENT_MODE_CHOICES = [
        ("CASH", "CASH"),
        ("CHEQUE", "CHEQUE"),
        ("BANK_TRANSFER", "BANK TRANSFER"),
        ("ONLINE", "ONLINE"),
        ("OTHER", "OTHER"),
    ]
    # Status choices
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirm", "Confirm"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("done", "Done"),
    ]
    # Basic information
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="event_bookings",
    )
    name = models.CharField(max_length=100)
    mobile_no = models.CharField(max_length=17)
    date = models.DateField(default=timezone.now)  # Booking creation date
    reference = models.CharField(max_length=50, unique=False)

    # Advance payment fields (now nullable)
    advance_amount = models.CharField(
        max_length=150, null=True, blank=True  # Allows NULL values in the database
    )
    advance_payment_mode = models.CharField(
        max_length=20, choices=ADVANCE_PAYMENT_MODE_CHOICES, null=True, blank=True
    )

    # Additional details
    description = models.TextField(blank=True)
    # Status field
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rule = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_event_bookings",
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.name} - {self.date}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def cancel_expired_pending_bookings(cls):
        # Local date because dates are naturally naive and we want the current local date
        today = timezone.localdate()

        # Find pending bookings that have an event_date that has past
        # .distinct() ensures we don't update the same booking multiple times if it has multiple past sessions.
        expired_bookings = cls.objects.filter(
            status="pending", sessions__event_date__lt=today
        ).distinct()

        if expired_bookings.exists():
            expired_bookings.update(status="cancelled")


class EventSession(models.Model):
    booking = models.ForeignKey(
        EventBooking, on_delete=models.CASCADE, related_name="sessions"
    )

    # Event details
    event_date = models.DateField()
    event_time = models.CharField(max_length=100)
    event_address = models.TextField(blank=True)

    # Session specifics
    per_dish_amount = models.CharField(max_length=150, blank=True, null=True)
    estimated_persons = models.CharField(max_length=150, blank=True, null=True)

    # Menu items for this specific session
    selected_items = models.JSONField(default=dict)

    # Extra services for this specific session
    extra_service_amount = models.CharField(max_length=250, blank=True, null=True)
    extra_service = models.JSONField(default=dict)

    # Waiter service details (support structured API payload)
    waiter_service_amount = models.CharField(max_length=250, blank=True, null=True)
    waiter_service = models.JSONField(default=dict, blank=True)

    # Vendors assigned to ingredients
    assigned_vendors = models.JSONField(default=dict, blank=True)

    # Outsourced items
    outsourced_items = models.JSONField(default=list, blank=True)

    # Ingredients added ad-hoc for this specific order (not in global recipes).
    # Shape: { "Ingredient Name": {"quantity": "28 kg", "category": "Grains", "for_item": "Biryani"} }
    order_local_ingredients = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["event_date", "event_time"]

    def __str__(self):
        return (
            f"Session for {self.booking.name} on {self.event_date} at {self.event_time}"
        )

    @property
    def formatted_event_date(self):
        return self.event_date.strftime("%d-%m-%Y")


class EventItemConfig(models.Model):
    event = models.ForeignKey(EventBooking, on_delete=models.CASCADE, related_name="item_configs")
    session = models.ForeignKey(EventSession, on_delete=models.CASCADE, related_name="item_configs")
    item_name = models.CharField(max_length=255)
    is_vendor_supplied = models.BooleanField(default=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="supplied_event_items")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=50, blank=True, default="")
    calculated_from_persons = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("session", "item_name")

    def __str__(self):
        vend_name = self.vendor.name if self.is_vendor_supplied and self.vendor else 'In-House'
        return f"{self.item_name} -> {vend_name} ({self.session.formatted_event_date})"


class IngredientVendorAssignment(models.Model):
    SOURCE_CHOICES = [
        ("item", "Item"),
        ("manual", "Manual"),
    ]
    ingredient = models.ForeignKey(IngridientsItem, on_delete=models.CASCADE, related_name="vendor_assignments")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="assigned_ingredients")
    event = models.ForeignKey(EventBooking, on_delete=models.CASCADE, related_name="ingredient_vendor_assignments")
    session = models.ForeignKey(EventSession, on_delete=models.CASCADE, related_name="ingredient_vendor_assignments")
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("ingredient", "session")

    def __str__(self):
        return f"{self.ingredient.name} -> {self.vendor.name} ({self.source_type})"

