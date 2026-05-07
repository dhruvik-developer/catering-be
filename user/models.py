from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import connection
from django.utils.text import slugify
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
    BRANCH_ROLE_MAIN_ADMIN = "main_admin"
    BRANCH_ROLE_BRANCH_ADMIN = "branch_admin"
    BRANCH_ROLE_BRANCH_USER = "branch_user"
    BRANCH_ROLE_CHOICES = (
        (BRANCH_ROLE_MAIN_ADMIN, "Main Tenant Admin"),
        (BRANCH_ROLE_BRANCH_ADMIN, "Branch Admin"),
        (BRANCH_ROLE_BRANCH_USER, "Branch User"),
    )

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )
    branch_profile = models.ForeignKey(
        "BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="users",
    )
    branch_role = models.CharField(
        max_length=30,
        choices=BRANCH_ROLE_CHOICES,
        default=BRANCH_ROLE_BRANCH_USER,
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


class BranchProfile(models.Model):
    name = models.CharField("Branch Name", max_length=150)
    branch_code = models.SlugField("Branch Code", max_length=60, unique=True, blank=True)
    city = models.CharField("City", max_length=100, blank=True)
    state = models.CharField("State", max_length=100, blank=True)
    address = models.TextField("Address", blank=True)
    phone_number = models.CharField("Phone Number", max_length=20, blank=True)
    email = models.EmailField("Email", blank=True)
    manager = models.ForeignKey(
        "UserModel",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="managed_branches",
    )
    is_main = models.BooleanField("Main Branch", default=False)
    is_active = models.BooleanField("Is Active", default=True)
    created_by = models.ForeignKey(
        "UserModel",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_branches",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "BranchProfile"
        verbose_name = "Branch Profile"
        verbose_name_plural = "Branch Profiles"
        ordering = ("-is_main", "city", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("name", "city"),
                name="unique_branch_profile_name_city",
            )
        ]

    def __str__(self):
        location = f" - {self.city}" if self.city else ""
        return f"{self.name}{location}"

    def _generate_branch_code(self):
        base = slugify(self.branch_code or self.name or self.city or "branch")[:45]
        if not base:
            base = "branch"

        candidate = base
        suffix = 2
        queryset = type(self).objects.all()
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)

        while queryset.filter(branch_code=candidate).exists():
            candidate = f"{base[:45 - len(str(suffix)) - 1]}-{suffix}"
            suffix += 1

        return candidate

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.branch_code = (self.branch_code or "").strip().lower()
        self.city = (self.city or "").strip()
        self.state = (self.state or "").strip()
        self.address = (self.address or "").strip()
        self.phone_number = (self.phone_number or "").strip()
        self.email = (self.email or "").strip()

        if not self.branch_code:
            self.branch_code = self._generate_branch_code()

        if not self.pk and not type(self).objects.exists():
            self.is_main = True

        super().save(*args, **kwargs)

        if self.is_main:
            type(self).objects.exclude(pk=self.pk).update(is_main=False)


class Note(models.Model):
    title = models.CharField(max_length=255)
    content = models.JSONField(default=list)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "Note"


class BusinessProfile(models.Model):
    LANGUAGE_ENGLISH = "en"
    LANGUAGE_GUJARATI = "gu"
    LANGUAGE_HINDI = "hi"
    LANGUAGE_CHOICES = (
        (LANGUAGE_ENGLISH, "English"),
        (LANGUAGE_GUJARATI, "Gujarati"),
        (LANGUAGE_HINDI, "Hindi"),
    )

    caters_name = models.CharField("Caters Name", max_length=255)
    phone_number = models.CharField("Phone Number", max_length=20)
    logo = models.ImageField("Logo", upload_to="business_profile/logos/", blank=True, null=True)
    color_code = models.CharField("Color Code", max_length=20, blank=True, null=True)
    selected_language = models.CharField(
        "Selected Language",
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default=LANGUAGE_ENGLISH,
    )
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
