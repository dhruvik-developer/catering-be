from django.db import models


class GroundCategory(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="ground_categories",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class GroundItem(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="ground_items",
    )
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        GroundCategory, on_delete=models.PROTECT, related_name="ground_items"
    )
    unit = models.CharField(max_length=30, default="Nos")
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "category"], name="unique_ground_item_per_category"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class GroundChecklistTemplate(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="ground_checklist_templates",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class GroundChecklistTemplateItem(models.Model):
    template = models.ForeignKey(
        GroundChecklistTemplate,
        on_delete=models.CASCADE,
        related_name="template_items",
    )
    ground_item = models.ForeignKey(
        GroundItem,
        on_delete=models.CASCADE,
        related_name="template_requirements",
    )
    required_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["template", "ground_item"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "ground_item"],
                name="unique_ground_item_per_template",
            )
        ]

    def __str__(self):
        return f"{self.template.name} - {self.ground_item.name}"


class EventGroundRequirement(models.Model):
    event_booking = models.ForeignKey(
        "eventbooking.EventBooking",
        on_delete=models.CASCADE,
        related_name="ground_requirements",
    )
    event_session = models.ForeignKey(
        "eventbooking.EventSession",
        on_delete=models.CASCADE,
        related_name="ground_requirements",
    )
    ground_item = models.ForeignKey(
        GroundItem,
        on_delete=models.PROTECT,
        related_name="event_requirements",
    )
    required_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    arranged_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_required = models.BooleanField(default=True)
    is_arranged = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_session", "ground_item"]
        constraints = [
            models.UniqueConstraint(
                fields=["event_booking", "event_session", "ground_item"],
                name="unique_ground_requirement_per_event_session_item",
            )
        ]

    def __str__(self):
        return (
            f"{self.event_booking.name} - {self.event_session.event_date} - {self.ground_item.name}"
        )

    def save(self, *args, **kwargs):
        if self.is_required and self.arranged_quantity >= self.required_quantity:
            self.is_arranged = True
        elif self.arranged_quantity <= 0:
            self.is_arranged = False
        super().save(*args, **kwargs)
