import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin


class SubscriptionPlan(models.Model):
    BILLING_CYCLE_MONTHLY = "monthly"
    BILLING_CYCLE_YEARLY = "yearly"
    BILLING_CYCLE_LIFETIME = "lifetime"

    BILLING_CYCLE_CHOICES = (
        (BILLING_CYCLE_MONTHLY, "Monthly"),
        (BILLING_CYCLE_YEARLY, "Yearly"),
        (BILLING_CYCLE_LIFETIME, "Lifetime"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CYCLE_CHOICES,
        default=BILLING_CYCLE_MONTHLY,
    )
    max_users = models.PositiveIntegerField(
        default=0,
        help_text="0 means unlimited users.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saas_subscription_plan"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Client(TenantMixin):
    STATUS_TRIALING = "trialing"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_SUSPENDED = "suspended"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_TRIALING, "Trialing"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past Due"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    name = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="clients",
    )
    subscription_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_TRIALING,
    )
    subscription_start_date = models.DateField(blank=True, null=True)
    subscription_end_date = models.DateField(blank=True, null=True)
    enabled_modules = models.ManyToManyField(
        "accesscontrol.PermissionModule",
        blank=True,
        related_name="clients",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_clients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        db_table = "tenant_client"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.schema_name})"

    @property
    def schema_status(self):
        return "ready"

    @property
    def schema_error(self):
        return ""

    @property
    def provisioned_at(self):
        return self.created_at

    @property
    def has_active_subscription(self):
        if self.schema_name == "public":
            return True
        if self.subscription_status not in {
            self.STATUS_TRIALING,
            self.STATUS_ACTIVE,
        }:
            return False
        if self.subscription_end_date and self.subscription_end_date < timezone.localdate():
            return False
        return True


class Domain(DomainMixin):
    class Meta:
        db_table = "tenant_domain"
        ordering = ("domain",)
