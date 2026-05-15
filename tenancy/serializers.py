from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django_tenants.utils import tenant_context
from rest_framework import serializers

from accesscontrol.models import PermissionModule
from tenancy.models import Client, Domain, SubscriptionPlan
from tenancy.services import (
    create_tenant_admin_user,
    create_tenant_domains,
    replace_tenant_domains,
)
from tenancy.utils import normalize_schema_name

MIN_PASSWORD_LENGTH = 8


def run_password_validators(value, user_instance=None):
    """Length check + Django's full AUTH_PASSWORD_VALIDATORS pipeline.

    Mirrors user.serializers.run_password_validators so both ways of provisioning
    a tenant admin (via user.serializers and via tenancy.serializers) reject
    weak passwords identically.
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


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    modules = serializers.SlugRelatedField(
        many=True,
        slug_field="code",
        queryset=PermissionModule.objects.filter(is_active=True),
        source="included_modules",
        required=False,
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

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
            "trial_days",
            "is_active",
            "modules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_description(self, value):
        # The model column is non-nullable TextField; normalise null -> "".
        return value or ""


class DomainSerializer(serializers.ModelSerializer):
    domain = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Domain
        fields = ["id", "domain", "is_primary"]
        read_only_fields = ["id"]


class ClientSummarySerializer(serializers.ModelSerializer):
    subscription_plan_name = serializers.CharField(
        source="subscription_plan.name",
        read_only=True,
    )
    enabled_modules = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field="code",
    )
    primary_domain = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "schema_name",
            "primary_domain",
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

    def get_primary_domain(self, obj):
        domain = obj.get_primary_domain()
        return domain.domain if domain else None


class TenantAdminCreateSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        UserModel = get_user_model()
        ghost = UserModel(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            attrs["password"] = run_password_validators(
                attrs.get("password"),
                user_instance=ghost,
            )
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail}) from exc
        return attrs


class ClientSerializer(serializers.ModelSerializer):
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
        source="subscription_plan.name",
        read_only=True,
    )
    enabled_modules = serializers.SlugRelatedField(
        many=True,
        slug_field="code",
        queryset=PermissionModule.objects.filter(is_active=True),
        required=False,
    )
    admin = TenantAdminCreateSerializer(write_only=True, required=False)
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )
    tenant_admins = serializers.SerializerMethodField()

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
            "tenant_admins",
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
            "tenant_admins",
        ]

    def get_primary_domain(self, obj):
        domain = obj.get_primary_domain()
        return domain.domain if domain else None

    def get_tenant_admins(self, obj):
        if getattr(obj, "schema_status", "") != "ready" or not obj.schema_name:
            return []

        UserModel = get_user_model()
        try:
            with tenant_context(obj):
                admins = list(
                    UserModel.objects.filter(
                        Q(branch_role=UserModel.BRANCH_ROLE_MAIN_ADMIN)
                        | Q(is_superuser=True)
                        | Q(is_staff=True)
                    ).order_by("date_joined")
                )
        except Exception:
            return []

        return [
            {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "branch_role": user.branch_role,
                "date_joined": user.date_joined,
            }
            for user in admins
        ]

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
        if self.instance and self.instance.schema_name != schema_name:
            raise serializers.ValidationError(
                "Schema name cannot be changed after the tenant is created."
            )
        return schema_name

    def _create_tenant_admin(self, client, admin_data):
        if not admin_data:
            return

        try:
            create_tenant_admin_user(client, admin_data)
        except ValueError as exc:
            raise serializers.ValidationError(
                {"admin": {"username": str(exc)}}
            ) from exc
        except RuntimeError as exc:
            raise serializers.ValidationError(
                {"admin": "Tenant admin user was not created in tenant schema."}
            ) from exc

    @transaction.atomic
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

        client = Client.objects.create(**validated_data)
        if enabled_modules:
            client.enabled_modules.set(enabled_modules)

        try:
            create_tenant_domains(client, domain=domain, domains=domains)
        except ValueError as exc:
            raise serializers.ValidationError({"domains": str(exc)}) from exc

        self._create_tenant_admin(client, admin_data)
        return client

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
