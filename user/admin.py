from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin

from accesscontrol.models import UserPermissionAssignment

from .models import SubscriptionPlan, Tenant, UserModel
from .tenanting import provision_tenant_schema

MIN_PASSWORD_LENGTH = 8


class TenantAdminForm(forms.ModelForm):
    create_admin_username = forms.CharField(
        required=False,
        label="Admin Username",
        help_text="Optional. Create the first login user for this tenant.",
    )
    create_admin_email = forms.EmailField(
        required=False,
        label="Admin Email",
    )
    create_admin_password = forms.CharField(
        required=False,
        label="Admin Password",
        widget=forms.PasswordInput(render_value=False),
        help_text="Optional. Required only when creating an admin username here.",
    )

    class Meta:
        model = Tenant
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

        if username and UserModel.objects.filter(username=username).exists():
            self.add_error("create_admin_username", "Username already exists.")

        return cleaned_data


class UserPermissionAssignmentInline(admin.TabularInline):
    model = UserPermissionAssignment
    extra = 0
    autocomplete_fields = ("permission",)
    fields = ("permission", "is_allowed", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(UserModel)
class CustomUserAdmin(UserAdmin):
    model = UserModel
    list_display = (
        "username",
        "email",
        "tenant",
        "tenant_schema",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    list_filter = ("tenant", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "tenant__name", "tenant__schema_name")
    ordering = ("username",)
    autocomplete_fields = ("tenant",)
    inlines = (UserPermissionAssignmentInline,)
    fieldsets = UserAdmin.fieldsets + (
        ("SaaS", {"fields": ("tenant",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("SaaS", {"fields": ("tenant",)}),
    )

    @admin.display(description="Tenant Schema")
    def tenant_schema(self, obj):
        return obj.tenant.schema_name if obj.tenant_id else "-"


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "price",
        "billing_cycle",
        "max_users",
        "tenant_count",
        "is_active",
    )
    list_filter = ("billing_cycle", "is_active")
    search_fields = ("name", "code")
    ordering = ("name",)

    @admin.display(description="Tenants")
    def tenant_count(self, obj):
        return obj.tenants.count()


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    form = TenantAdminForm
    list_display = (
        "name",
        "schema_name",
        "subscription_plan",
        "subscription_status",
        "schema_status",
        "module_count",
        "user_count",
    )
    list_filter = ("subscription_status", "schema_status", "subscription_plan")
    search_fields = ("name", "schema_name", "contact_email", "contact_phone")
    autocomplete_fields = ("subscription_plan", "created_by")
    filter_horizontal = ("enabled_modules",)
    readonly_fields = (
        "schema_status",
        "schema_error",
        "provisioned_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    actions = ("provision_selected_tenant_schemas",)
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
                    "enabled_modules",
                )
            },
        ),
        (
            "Schema",
            {
                "fields": (
                    "schema_status",
                    "schema_error",
                    "provisioned_at",
                )
            },
        ),
        (
            "Create Tenant Admin Login",
            {
                "fields": (
                    "create_admin_username",
                    "create_admin_email",
                    "create_admin_password",
                ),
                "description": (
                    "Tenant itself does not log in. Use these optional fields to "
                    "create the first admin user for this tenant."
                ),
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

        username = form.cleaned_data.get("create_admin_username")
        password = form.cleaned_data.get("create_admin_password")
        email = form.cleaned_data.get("create_admin_email") or ""

        if username and password:
            UserModel.objects.create_user(
                username=username,
                email=email,
                password=password,
                tenant=obj,
                is_staff=True,
            )
            self.message_user(
                request,
                f"Tenant admin user '{username}' created.",
                level=messages.SUCCESS,
            )

    @admin.display(description="Modules")
    def module_count(self, obj):
        return obj.enabled_modules.count()

    @admin.display(description="Users")
    def user_count(self, obj):
        return obj.users.count()

    @admin.action(description="Provision selected tenant schemas")
    def provision_selected_tenant_schemas(self, request, queryset):
        success_count = 0
        for tenant in queryset:
            try:
                provision_tenant_schema(tenant)
            except Exception as exc:
                self.message_user(
                    request,
                    f"{tenant.name}: schema provisioning failed: {exc}",
                    level=messages.ERROR,
                )
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Provisioned {success_count} tenant schema(s).",
                level=messages.SUCCESS,
            )
