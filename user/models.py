from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
import uuid


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
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
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
        db_table = "subscription_plan"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Tenant(models.Model):
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

    SCHEMA_PENDING = "pending"
    SCHEMA_READY = "ready"
    SCHEMA_SKIPPED = "skipped"
    SCHEMA_FAILED = "failed"

    SCHEMA_STATUS_CHOICES = (
        (SCHEMA_PENDING, "Pending"),
        (SCHEMA_READY, "Ready"),
        (SCHEMA_SKIPPED, "Skipped"),
        (SCHEMA_FAILED, "Failed"),
    )

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )
    name = models.CharField(max_length=150)
    schema_name = models.SlugField(max_length=63, unique=True)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="tenants",
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
        related_name="tenants",
    )
    schema_status = models.CharField(
        max_length=20,
        choices=SCHEMA_STATUS_CHOICES,
        default=SCHEMA_PENDING,
    )
    schema_error = models.TextField(blank=True)
    provisioned_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_tenants",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.schema_name})"

    @property
    def has_active_subscription(self):
        if self.subscription_status not in {
            self.STATUS_TRIALING,
            self.STATUS_ACTIVE,
        }:
            return False
        if self.subscription_end_date and self.subscription_end_date < timezone.localdate():
            return False
        return True

    def mark_schema_ready(self):
        self.schema_status = self.SCHEMA_READY
        self.schema_error = ""
        self.provisioned_at = timezone.now()
        self.save(update_fields=["schema_status", "schema_error", "provisioned_at", "updated_at"])

    def mark_schema_skipped(self, reason):
        self.schema_status = self.SCHEMA_SKIPPED
        self.schema_error = reason
        self.provisioned_at = timezone.now()
        self.save(update_fields=["schema_status", "schema_error", "provisioned_at", "updated_at"])

    def mark_schema_failed(self, error):
        self.schema_status = self.SCHEMA_FAILED
        self.schema_error = str(error)
        self.save(update_fields=["schema_status", "schema_error", "updated_at"])


class UserModel(AbstractUser):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="users",
        help_text="Tenant/customer account this user belongs to. Empty means platform user.",
    )

    @property
    def tokens(self):
        refresh = RefreshToken.for_user(self)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}

    class Meta:
        db_table = "user"


class Note(models.Model):
    title = models.CharField(max_length=255)
    content = models.JSONField(default=list)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "Note"


class BusinessProfile(models.Model):
    caters_name = models.CharField("Caters Name", max_length=255)
    phone_number = models.CharField("Phone Number", max_length=20)
    logo = models.ImageField("Logo", upload_to="business_profile/logos/", blank=True, null=True)
    color_code = models.CharField("Color Code", max_length=20, blank=True, null=True)
    whatsapp_number = models.CharField(
        "WhatsApp Number", max_length=20, blank=True, null=True
    )
    fssai_number = models.CharField(
        "FSSAI Number", max_length=50, blank=True, null=True
    )
    godown_address = models.TextField("Godown Address", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.caters_name

    class Meta:
        db_table = "BusinessProfile"
        verbose_name = "Business Profile"
        verbose_name_plural = "Business Profiles"
