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


def _extract_vendor_ids_from_session_data(session):
    """Collect every Vendor.id referenced by a session — looks at both the
    relational `IngredientVendorAssignment` rows and the JSON-blob fields
    (`assigned_vendors`, `outsourced_items`). Used by
    `sync_vendor_assignments_for_session()` to upsert the per-session vendor
    workflow rows below."""
    vendor_ids = set()

    # `assigned_vendors` shape: {ingredient_name: {"id": <vendor_id>, ...}}
    assigned = getattr(session, "assigned_vendors", None) or {}
    if isinstance(assigned, dict):
        for entry in assigned.values():
            if isinstance(entry, dict):
                raw = entry.get("id") or entry.get("vendor_id")
                if raw is not None:
                    try:
                        vendor_ids.add(int(raw))
                    except (TypeError, ValueError):
                        pass

    # `outsourced_items` shape: [{"vendor": {"id": <vendor_id>, ...}, ...}]
    outsourced = getattr(session, "outsourced_items", None) or []
    if isinstance(outsourced, list):
        for item in outsourced:
            if not isinstance(item, dict):
                continue
            vend = item.get("vendor")
            if isinstance(vend, dict):
                raw = vend.get("id") or vend.get("vendor_id")
                if raw is not None:
                    try:
                        vendor_ids.add(int(raw))
                    except (TypeError, ValueError):
                        pass

    # Relational source (IngredientVendorAssignment defined below — query
    # only if the session is saved, otherwise reverse FK lookups raise).
    if getattr(session, "pk", None) is not None:
        try:
            ids = session.ingredient_vendor_assignments.values_list(
                "vendor_id", flat=True
            )
            vendor_ids.update(int(v) for v in ids if v is not None)
        except Exception:
            # Reverse-FK access can fail if the related model hasn't been
            # migrated yet (first-time setup); auto-sync is best-effort.
            pass

    return vendor_ids


def sync_vendor_assignments_for_session(session):
    """Upsert `EventVendorAssignment` rows for every Vendor referenced by the
    session. Called after EventSession / IngredientVendorAssignment save.
    Safe to call repeatedly — new rows are pending by default, existing rows
    are left untouched (we never auto-revert an accepted/declined row)."""
    if getattr(session, "pk", None) is None:
        return
    vendor_ids = _extract_vendor_ids_from_session_data(session)
    if not vendor_ids:
        return
    for vendor_id in vendor_ids:
        EventVendorAssignment.objects.get_or_create(
            session=session,
            vendor_id=vendor_id,
        )


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-create vendor workflow rows for every vendor referenced by
        # this session's JSON fields. Idempotent — only inserts missing rows.
        sync_vendor_assignments_for_session(self)


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # When admin assigns a vendor to a raw ingredient, ensure that vendor
        # has a session-level EventVendorAssignment so the vendor sees this
        # session in their portal.
        sync_vendor_assignments_for_session(self.session)



class SessionChecklistTick(models.Model):
    """One row per (session, item_key, action) checkbox the user has touched on
    the per-session checklist screen. Lets the mobile / web checklist show the
    previous tick state when reopened and gives admins a verification trail
    (`ticked_by` + `ticked_at`).

    The `item_key` is a stable client-built string that identifies the row
    within the session payload — e.g. `menu:Roti::Butter Roti`,
    `ingredient:Tameta`, `vendor:reerrree`. It's intentionally NOT a database
    FK because the rows are derived from JSON fields (`selected_items`,
    `ingredients_required`, `assigned_vendors`, `outsourced_items`,
    `ground_management`) which don't have stable per-row IDs.
    """

    ACTION_PREPARED = "prepared"
    ACTION_SERVED = "served"
    ACTION_RECEIVED = "received"
    ACTION_DELIVERED = "delivered"
    ACTION_AVAILABLE = "available"
    ACTION_CHOICES = (
        (ACTION_PREPARED, "Prepared"),
        (ACTION_SERVED, "Served"),
        (ACTION_RECEIVED, "Received"),
        (ACTION_DELIVERED, "Delivered"),
        (ACTION_AVAILABLE, "Available"),
    )

    session = models.ForeignKey(
        EventSession,
        on_delete=models.CASCADE,
        related_name="checklist_ticks",
    )
    item_key = models.CharField(max_length=255)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    is_done = models.BooleanField(default=False)
    ticked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="session_checklist_ticks",
    )
    ticked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("session", "item_key", "action")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "item_key", "action"),
                name="uniq_session_checklist_tick",
            ),
        ]

    def __str__(self):
        return f"{self.session_id}/{self.item_key}/{self.action}={self.is_done}"


class EventVendorAssignment(models.Model):
    """One row per (session, vendor). Mirrors `EventStaffAssignment` for the
    vendor side of the workflow: pending → accepted / declined, plus driver
    + ETA captured when the vendor marks the session as dispatched.

    Rows are auto-created from `EventSession.assigned_vendors` (ingredient
    vendors) and `EventSession.outsourced_items[*].vendor` on session save so
    admins don't have to manage them by hand. The unique constraint on
    (session, vendor) makes the upsert race-safe."""

    RESPONSE_PENDING = "pending"
    RESPONSE_ACCEPTED = "accepted"
    RESPONSE_DECLINED = "declined"
    RESPONSE_STATUS_CHOICES = (
        (RESPONSE_PENDING, "Pending"),
        (RESPONSE_ACCEPTED, "Accepted"),
        (RESPONSE_DECLINED, "Declined"),
    )

    session = models.ForeignKey(
        EventSession,
        on_delete=models.CASCADE,
        related_name="vendor_assignments",
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="event_vendor_assignments",
    )

    # Session-level accept/decline. Per-item partial decline lives in
    # `declined_item_keys` below — see _assignment_payload in the serializer
    # for the wire shape.
    response_status = models.CharField(
        max_length=12,
        choices=RESPONSE_STATUS_CHOICES,
        default=RESPONSE_PENDING,
    )
    decline_reason = models.TextField(blank=True, default="")
    responded_at = models.DateTimeField(null=True, blank=True)

    # List of `item_key`s the vendor declined individually (still accepting
    # the session overall). Same `item_key` shape used by
    # `SessionChecklistTick` — e.g. "ingredient:Onion" or
    # "outsourced:Pizza::Pizza Counter". An empty list means "no per-item
    # exceptions", which is the default.
    declined_item_keys = models.JSONField(default=list, blank=True)

    # Driver / dispatch capture. Filled in when the vendor taps "Dispatched"
    # on the mobile app — surfaces to staff/receiver so they know who's
    # bringing the delivery and when.
    driver_name = models.CharField(max_length=120, blank=True, default="")
    driver_phone = models.CharField(max_length=30, blank=True, default="")
    driver_eta = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Event Vendor Assignment"
        verbose_name_plural = "Event Vendor Assignments"
        unique_together = ("session", "vendor")
        ordering = ("session", "vendor")

    def __str__(self):
        return f"{self.vendor.name} -> session {self.session_id} ({self.response_status})"

    @property
    def is_dispatched(self):
        return self.dispatched_at is not None


class EventVendorAssignmentResponse(models.Model):
    """Append-only log of every vendor accept/decline action. Same shape as
    `EventStaffAssignmentResponse` so admins can read a unified timeline of
    who responded when (and why if declined)."""

    RESPONSE_ACCEPTED = EventVendorAssignment.RESPONSE_ACCEPTED
    RESPONSE_DECLINED = EventVendorAssignment.RESPONSE_DECLINED
    RESPONSE_CHOICES = (
        (RESPONSE_ACCEPTED, "Accepted"),
        (RESPONSE_DECLINED, "Declined"),
    )

    assignment = models.ForeignKey(
        EventVendorAssignment,
        on_delete=models.CASCADE,
        related_name="response_history",
    )
    # When non-blank, identifies which sub-item the response was for —
    # matches the `item_key` shape on `SessionChecklistTick`. Empty string
    # means session-level response.
    item_key = models.CharField(max_length=255, blank=True, default="")
    response = models.CharField(max_length=12, choices=RESPONSE_CHOICES)
    reason = models.TextField(blank=True, default="")
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_assignment_responses",
    )
    responded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Event Vendor Assignment Response"
        verbose_name_plural = "Event Vendor Assignment Responses"
        ordering = ("-responded_at",)

    def __str__(self):
        return f"{self.assignment_id}/{self.item_key or 'session'} -> {self.response}"
