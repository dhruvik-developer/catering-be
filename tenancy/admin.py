from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context

from tenancy.models import Client, Domain, SubscriptionPlan
from user.models import BusinessProfile

MIN_PASSWORD_LENGTH = 8
UserModel = get_user_model()


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1
    min_num = 1
    validate_min = True


class ClientAdminForm(forms.ModelForm):
    create_admin_username = forms.CharField(
        required=False,
        label="Admin Username",
        help_text="Optional. Create the first login user inside this tenant schema.",
    )
    create_admin_email = forms.EmailField(required=False, label="Admin Email")
    create_admin_password = forms.CharField(
        required=False,
        label="Admin Password",
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = Client
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("create_admin_username")
        password = cleaned_data.get("create_admin_password")

        if username and not password:
            self.add_error(
                "create_admin_password",
                "Password is required when creating a tenant admin login.",
            )
        if password and len(password) < MIN_PASSWORD_LENGTH:
            self.add_error(
                "create_admin_password",
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.",
            )
        return cleaned_data


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    form = ClientAdminForm
    list_display = (
        "name",
        "schema_name",
        "primary_domain",
        "subscription_plan",
        "subscription_status",
        "module_count",
    )
    list_filter = ("subscription_status", "subscription_plan")
    search_fields = ("name", "schema_name", "contact_email", "contact_phone")
    autocomplete_fields = ("subscription_plan", "created_by")
    inlines = [DomainInline]
    readonly_fields = ("created_by", "created_at", "updated_at")
    fieldsets = (
        (
            "Tenant",
            {
                "fields": (
                    "name",
                    "schema_name",
                    "contact_name",
                    "contact_email",
                    "contact_phone",
                )
            },
        ),
        (
            "Subscription",
            {
                "fields": (
                    "subscription_plan",
                    "subscription_status",
                    "subscription_start_date",
                    "subscription_end_date",
                ),
                "description": (
                    "Modules are inherited automatically from the selected "
                    "Subscription Plan. Configure modules on the plan, not here."
                ),
            },
        ),
        (
            "Create Tenant Admin Login",
            {
                "fields": (
                    "create_admin_username",
                    "create_admin_email",
                    "create_admin_password",
                )
            },
        ),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

        username = form.cleaned_data.get("create_admin_username")
        password = form.cleaned_data.get("create_admin_password")
        email = form.cleaned_data.get("create_admin_email") or ""

        with schema_context(obj.schema_name):
            if username and password:
                UserModel.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    is_active=True,
                    is_staff=True,
                )
                self.message_user(
                    request,
                    f"Tenant admin user '{username}' created in schema '{obj.schema_name}'.",
                    level=messages.SUCCESS,
                )

            if not change and not BusinessProfile.objects.exists():
                BusinessProfile.objects.create(
                    caters_name=obj.name,
                    phone_number=obj.contact_phone or "",
                )

    @admin.display(description="Primary Domain")
    def primary_domain(self, obj):
        domain = obj.get_primary_domain()
        return domain.domain if domain else "-"

    @admin.display(description="Modules")
    def module_count(self, obj):
        return obj.enabled_modules.count()


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain", "tenant__name", "tenant__schema_name")
    autocomplete_fields = ("tenant",)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "price",
        "billing_cycle",
        "max_users",
        "module_count",
        "client_count",
        "is_active",
    )
    list_filter = ("billing_cycle", "is_active")
    search_fields = ("name", "code")
    ordering = ("name",)
    filter_horizontal = ("included_modules",)

    @admin.display(description="Tenants")
    def client_count(self, obj):
        return obj.clients.count()

    @admin.display(description="Modules")
    def module_count(self, obj):
        return obj.included_modules.count()
