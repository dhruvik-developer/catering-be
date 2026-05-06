from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.conf import settings
from django_tenants.utils import tenant_context
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)
from radha.Utils.permissions import get_tenant_enabled_module_codes, get_user_active_tenant
from tenancy.serializers import ClientSummarySerializer, DomainSerializer
from tenancy.services import (
    create_tenant_admin_user,
    create_tenant_domains,
    replace_tenant_domains,
)
from user.tenanting import normalize_schema_name, provision_tenant_schema

from tenancy.models import Client, SubscriptionPlan
from .models import BusinessProfile, Note, UserModel


def seed_tenant_business_profile(tenant):
    """Create the initial BusinessProfile inside the tenant schema.

    Called once during tenant provisioning so the tenant lands with a profile
    pre-populated from their tenant record (caters_name <- tenant.name,
    phone_number <- tenant.contact_phone). The tenant admin can edit it later
    from Settings.
    """
    caters_name = (tenant.name or "").strip()
    phone_number = (tenant.contact_phone or "").strip()
    if not caters_name:
        return None

    with tenant_context(tenant):
        if getattr(connection, "schema_name", "public") != tenant.schema_name:
            return None
        if BusinessProfile.objects.exists():
            return None
        return BusinessProfile.objects.create(
            caters_name=caters_name[:255],
            phone_number=phone_number[:20],
        )

MIN_PASSWORD_LENGTH = 8


def run_password_validators(value, user_instance=None):
    """Run AUTH_PASSWORD_VALIDATORS + the project's MIN_PASSWORD_LENGTH check.

    All three places we set passwords go through this so a weak password is
    blocked consistently — common-list check, numeric-only check, and the
    UserAttributeSimilarity check from settings all fire here.
    """
    if not value or len(value) < MIN_PASSWORD_LENGTH:
        raise serializers.ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    try:
        django_validate_password(value, user=user_instance)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    tenant = serializers.CharField(required=False, allow_blank=True, write_only=True)
    tenant_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    schema_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    domain = serializers.CharField(required=False, allow_blank=True, write_only=True)


class NoteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Note
        fields = ["id", "title", "content"]


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "code",
            "description",
            "price",
            "billing_cycle",
            "max_users",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantSummarySerializer(serializers.ModelSerializer):
    subscription_plan_name = serializers.CharField(
        source="subscription_plan.name", read_only=True
    )
    enabled_modules = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field="code",
    )

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "schema_name",
            "subscription_plan",
            "subscription_plan_name",
            "subscription_status",
            "subscription_start_date",
            "subscription_end_date",
            "enabled_modules",
            "schema_status",
            "schema_error",
            "provisioned_at",
        ]
        read_only_fields = fields


class TenantAdminCreateSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate_password(self, value):
        return run_password_validators(value)


class TenantSerializer(serializers.ModelSerializer):
    schema_name = serializers.CharField(required=False, allow_blank=True)
    domain = serializers.CharField(required=False, allow_blank=True, write_only=True)
    primary_domain = serializers.SerializerMethodField()
    domains = DomainSerializer(many=True, required=False)
    subscription_plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    subscription_plan_name = serializers.CharField(
        source="subscription_plan.name", read_only=True
    )
    enabled_modules = serializers.SlugRelatedField(
        many=True,
        slug_field="code",
        queryset=PermissionModule.objects.filter(is_active=True),
        required=False,
    )
    admin = TenantAdminCreateSerializer(write_only=True, required=False)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "schema_name",
            "domain",
            "primary_domain",
            "domains",
            "contact_name",
            "contact_email",
            "contact_phone",
            "subscription_plan",
            "subscription_plan_name",
            "subscription_status",
            "subscription_start_date",
            "subscription_end_date",
            "enabled_modules",
            "schema_status",
            "schema_error",
            "provisioned_at",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
            "admin",
        ]
        read_only_fields = [
            "id",
            "primary_domain",
            "schema_status",
            "schema_error",
            "provisioned_at",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "schema_name": {"required": False},
        }

    def get_primary_domain(self, obj):
        domain = obj.get_primary_domain()
        return domain.domain if domain else None

    def _get_unique_schema_name(self, value):
        try:
            base_schema_name = normalize_schema_name(value)
        except ValueError as exc:
            raise serializers.ValidationError({"schema_name": str(exc)}) from exc
        schema_name = base_schema_name
        suffix = 2

        while Client.objects.filter(schema_name=schema_name).exists():
            suffix_text = f"_{suffix}"
            schema_name = f"{base_schema_name[:63 - len(suffix_text)]}{suffix_text}"
            suffix += 1

        return schema_name

    def validate_schema_name(self, value):
        try:
            schema_name = normalize_schema_name(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        duplicate_query = Client.objects.filter(schema_name=schema_name)
        if self.instance:
            duplicate_query = duplicate_query.exclude(pk=self.instance.pk)
        if duplicate_query.exists():
            raise serializers.ValidationError("Schema name already exists.")
        if (
            self.instance
            and self.instance.schema_name != schema_name
            and self.instance.schema_status == "ready"
        ):
            raise serializers.ValidationError(
                "Schema name cannot be changed after the tenant schema is ready."
            )
        return schema_name

    def create(self, validated_data):
        request = self.context.get("request")
        enabled_modules = validated_data.pop("enabled_modules", [])
        admin_data = validated_data.pop("admin", None)
        domain = validated_data.pop("domain", "")
        domains = validated_data.pop("domains", None)

        if not validated_data.get("schema_name"):
            validated_data["schema_name"] = self._get_unique_schema_name(
                validated_data["name"]
            )
        else:
            validated_data["schema_name"] = normalize_schema_name(
                validated_data["schema_name"]
            )

        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user

        tenant = Client.objects.create(**validated_data)
        if enabled_modules:
            tenant.enabled_modules.set(enabled_modules)

        try:
            create_tenant_domains(tenant, domain=domain, domains=domains)
        except ValueError as exc:
            raise serializers.ValidationError({"domains": str(exc)}) from exc

        provision_tenant_schema(tenant)

        # Seed the tenant's BusinessProfile from their contact info so they
        # don't have to re-type it on first login.
        try:
            seed_tenant_business_profile(tenant)
        except Exception:
            # Don't fail tenant creation if seeding the profile fails — the
            # admin can create it manually from Settings.
            pass

        if admin_data:
            try:
                create_tenant_admin_user(tenant, admin_data)
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"admin": {"username": str(exc)}}
                ) from exc
            except RuntimeError as exc:
                raise serializers.ValidationError(
                    {"admin": "Tenant admin user was not created in tenant schema."}
                ) from exc

        return tenant

    def update(self, instance, validated_data):
        enabled_modules = validated_data.pop("enabled_modules", None)
        validated_data.pop("admin", None)
        domain = validated_data.pop("domain", None)
        domains = validated_data.pop("domains", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if enabled_modules is not None:
            instance.enabled_modules.set(enabled_modules)

        if domain is not None or domains is not None:
            try:
                replace_tenant_domains(
                    instance,
                    domain=domain or "",
                    domains=domains,
                )
            except ValueError as exc:
                raise serializers.ValidationError({"domains": str(exc)}) from exc

        return instance


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    tenant = serializers.SerializerMethodField()
    tenant_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    is_staff = serializers.BooleanField(required=False, default=False)
    module_codes = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    allowed_permissions = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = UserModel
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "tenant",
            "tenant_id",
            "is_staff",
            "is_active",
            "module_codes",
            "allowed_permissions",
        ]
        read_only_fields = ["id", "tenant"]

    def _resolve_tenant(self, attrs):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")

        actor = request.user
        active_tenant = getattr(request, "tenant", None)
        if (
            active_tenant is not None
            and getattr(active_tenant, "schema_name", "public") != "public"
        ):
            if actor.is_staff:
                if attrs.get("is_staff"):
                    raise PermissionDenied(
                        "Tenant admin cannot create another admin user."
                    )
                actor._active_tenant = active_tenant
                return active_tenant
            raise PermissionDenied("Only tenant admin can create this resource.")

        if actor.is_superuser:
            return None

        if actor.is_staff and getattr(actor, "tenant_id", None):
            if attrs.get("is_staff"):
                raise PermissionDenied("Tenant admin cannot create another admin user.")
            return actor.tenant

        raise PermissionDenied("Only platform admin or tenant admin allowed.")

    def _validate_plan_user_limit(self, tenant):
        if tenant is None or tenant.subscription_plan is None:
            return

        max_users = tenant.subscription_plan.max_users
        user_count = tenant.users.count() if hasattr(tenant, "users") else UserModel.objects.count()
        if max_users and user_count >= max_users:
            raise serializers.ValidationError(
                {"tenant_id": "Tenant subscription user limit reached."}
            )

    def _validate_requested_modules(self, tenant, module_codes, permission_codes):
        requested_module_codes = set(module_codes)
        unknown_modules = requested_module_codes - set(
            PermissionModule.objects.filter(
                code__in=requested_module_codes,
                is_active=True,
            ).values_list("code", flat=True)
        )

        if unknown_modules:
            raise serializers.ValidationError(
                {
                    "module_codes": (
                        f"Unknown module codes: {', '.join(sorted(unknown_modules))}"
                    )
                }
            )

        requested_permission_codes = set(permission_codes)
        permissions = AccessPermission.objects.filter(
            code__in=requested_permission_codes,
            is_active=True,
            module__is_active=True,
        ).select_related("module")
        known_permission_codes = {permission.code for permission in permissions}
        unknown_permissions = requested_permission_codes - known_permission_codes

        if unknown_permissions:
            raise serializers.ValidationError(
                {
                    "allowed_permissions": (
                        "Unknown permission codes: "
                        f"{', '.join(sorted(unknown_permissions))}"
                    )
                }
            )

        if tenant is None:
            return

        if not tenant.has_active_subscription:
            raise serializers.ValidationError(
                {"tenant_id": "Tenant subscription is not active."}
            )

        actor = self.context.get("request").user
        actor._active_tenant = tenant
        enabled_modules = get_tenant_enabled_module_codes(actor)
        disallowed_modules = requested_module_codes - enabled_modules
        disallowed_permissions = {
            permission.code
            for permission in permissions
            if permission.module.code not in enabled_modules
        }

        if disallowed_modules:
            raise serializers.ValidationError(
                {
                    "module_codes": (
                        "Tenant subscription does not include modules: "
                        f"{', '.join(sorted(disallowed_modules))}"
                    )
                }
            )

        if disallowed_permissions:
            raise serializers.ValidationError(
                {
                    "allowed_permissions": (
                        "Tenant subscription does not include permissions: "
                        f"{', '.join(sorted(disallowed_permissions))}"
                    )
                }
            )

    def validate(self, attrs):
        tenant = self._resolve_tenant(attrs)
        self._validate_plan_user_limit(tenant)
        self._validate_requested_modules(
            tenant=tenant,
            module_codes=attrs.get("module_codes", []),
            permission_codes=attrs.get("allowed_permissions", []),
        )
        attrs["_tenant"] = tenant
        return attrs

    def create(self, validated_data):
        tenant = validated_data.pop("_tenant", None)
        module_codes = set(validated_data.pop("module_codes", []))
        allowed_permissions = set(validated_data.pop("allowed_permissions", []))
        validated_data.pop("tenant_id", None)

        create_kwargs = {
            "username": validated_data["username"],
            "email": validated_data.get("email", ""),
            "password": validated_data["password"],
            "first_name": validated_data.get("first_name", ""),
            "last_name": validated_data.get("last_name", ""),
            "is_staff": validated_data.get("is_staff", False),
            "is_active": validated_data.get("is_active", True),
        }
        if tenant is not None and hasattr(tenant, "users"):
            create_kwargs["tenant"] = tenant

        user = UserModel.objects.create_user(
            **create_kwargs,
        )

        permission_codes = set(allowed_permissions)
        if module_codes:
            permission_codes.update(
                AccessPermission.objects.filter(
                    module__code__in=module_codes,
                    is_active=True,
                    module__is_active=True,
                ).values_list("code", flat=True)
            )

        permissions = AccessPermission.objects.filter(code__in=permission_codes)
        for permission in permissions:
            UserPermissionAssignment.objects.update_or_create(
                user=user,
                permission=permission,
                defaults={"is_allowed": True},
            )

        return user

    def get_tenant(self, obj):
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            tenant = get_user_active_tenant(obj)
        if tenant is None or not hasattr(tenant, "schema_name"):
            return None
        if not hasattr(tenant, "get_primary_domain"):
            return TenantSummarySerializer(tenant).data
        return ClientSummarySerializer(tenant).data

    def validate_password(self, value):
        attrs = self.initial_data or {}
        ghost = UserModel(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        return run_password_validators(value, user_instance=ghost)


class ChangePasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):

        return run_password_validators(value, user_instance=self.context.get("target_user"))


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = [
            "id",
            "caters_name",
            "phone_number",
            "logo",
            "color_code",
            "selected_language",
            "whatsapp_number",
            "fssai_number",
            "godown_address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_logo(self, value):
        if value is None:
            return value

        max_bytes = getattr(settings, "BUSINESS_PROFILE_LOGO_MAX_BYTES", 2 * 1024 * 1024)
        if value.size > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            raise serializers.ValidationError(
                f"Logo file size must be {max_mb:.1f} MB or smaller."
            )

        allowed_types = getattr(
            settings,
            "BUSINESS_PROFILE_LOGO_ALLOWED_TYPES",
            ("image/jpeg", "image/png", "image/webp"),
        )
        content_type = getattr(value, "content_type", "")
        if content_type and content_type not in allowed_types:
            raise serializers.ValidationError(
                "Logo must be a JPEG, PNG, or WebP image."
            )

        return value


class BusinessProfileLanguageSerializer(serializers.Serializer):
    selected_language = serializers.ChoiceField(
        choices=BusinessProfile.LANGUAGE_CHOICES
    )
