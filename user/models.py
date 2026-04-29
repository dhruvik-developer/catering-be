from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import connection
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


class UserModel(AbstractUser):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )

    @property
    def tokens(self):
        refresh = RefreshToken.for_user(self)
        schema_name = getattr(connection, "schema_name", "public")
        tenant = getattr(connection, "tenant", None)
        refresh["schema_name"] = schema_name
        refresh["tenant_domain"] = getattr(tenant, "domain_url", None) or ""
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
