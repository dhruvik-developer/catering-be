from django.contrib.auth import get_user_model
from rest_framework import serializers

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    UserPermissionAssignment,
)
from radha.Utils.permissions import get_effective_permission_codes


UserModel = get_user_model()


class AccessPermissionSerializer(serializers.ModelSerializer):
    module_code = serializers.CharField(source="module.code", read_only=True)
    module_name = serializers.CharField(source="module.name", read_only=True)

    class Meta:
        model = AccessPermission
        fields = (
            "id",
            "code",
            "name",
            "description",
            "action",
            "module_code",
            "module_name",
            "sort_order",
            "is_active",
        )


class PermissionModuleSerializer(serializers.ModelSerializer):
    permissions = AccessPermissionSerializer(many=True, read_only=True)

    class Meta:
        model = PermissionModule
        fields = (
            "id",
            "code",
            "name",
            "description",
            "sort_order",
            "is_active",
            "permissions",
        )


class PermissionSubjectSerializer(serializers.ModelSerializer):
    user_type = serializers.SerializerMethodField()
    profile_name = serializers.SerializerMethodField()
    staff_role = serializers.SerializerMethodField()
    tenant_id = serializers.SerializerMethodField()
    tenant_name = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = UserModel
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "tenant_id",
            "tenant_name",
            "user_type",
            "profile_name",
            "staff_role",
            "effective_permissions",
        )

    def get_user_type(self, obj):
        if obj.is_superuser or obj.is_staff:
            return "admin"
        if hasattr(obj, "staff_profile"):
            return "staff"
        if hasattr(obj, "vendor_profile"):
            return "vendor"
        return "user"

    def get_profile_name(self, obj):
        if hasattr(obj, "staff_profile"):
            return obj.staff_profile.name
        if hasattr(obj, "vendor_profile"):
            return obj.vendor_profile.name
        return obj.get_full_name().strip() or obj.username

    def get_staff_role(self, obj):
        if hasattr(obj, "staff_profile") and obj.staff_profile.role:
            return obj.staff_profile.role.name
        return None

    def get_tenant_id(self, obj):
        return str(obj.tenant_id) if obj.tenant_id else None

    def get_tenant_name(self, obj):
        return obj.tenant.name if obj.tenant_id else None

    def get_effective_permissions(self, obj):
        return sorted(get_effective_permission_codes(obj))


class UserPermissionAssignmentWriteSerializer(serializers.Serializer):
    allowed_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    denied_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        allowed = set(attrs.get("allowed_permissions", []))
        denied = set(attrs.get("denied_permissions", []))
        unknown_codes = (
            allowed | denied
        ) - set(AccessPermission.objects.values_list("code", flat=True))

        if unknown_codes:
            raise serializers.ValidationError(
                {
                    "permissions": (
                        f"Unknown permission codes: {', '.join(sorted(unknown_codes))}"
                    )
                }
            )

        overlap = allowed & denied
        if overlap:
            raise serializers.ValidationError(
                {
                    "permissions": (
                        f"Same permission cannot be both allowed and denied: {', '.join(sorted(overlap))}"
                    )
                }
            )

        request = self.context.get("request")
        tenant = getattr(getattr(request, "user", None), "tenant", None)
        if tenant:
            if not tenant.has_active_subscription:
                raise serializers.ValidationError(
                    {"tenant": "Tenant subscription is not active."}
                )

            enabled_modules = set(
                tenant.enabled_modules.filter(is_active=True).values_list("code", flat=True)
            )
            disallowed_codes = set(
                AccessPermission.objects.filter(code__in=allowed | denied)
                .exclude(module__code__in=enabled_modules)
                .values_list("code", flat=True)
            )

            if disallowed_codes:
                raise serializers.ValidationError(
                    {
                        "permissions": (
                            "Tenant subscription does not include permissions: "
                            f"{', '.join(sorted(disallowed_codes))}"
                        )
                    }
                )

        return attrs


class UserPermissionAssignmentDetailSerializer(serializers.Serializer):
    user = PermissionSubjectSerializer(read_only=True)
    direct_permissions = serializers.ListField(child=serializers.DictField(), read_only=True)
    effective_permissions = serializers.ListField(child=serializers.CharField(), read_only=True)


def build_user_permission_payload(user):
    assignment_qs = UserPermissionAssignment.objects.filter(user=user).select_related(
        "permission", "permission__module"
    )
    if user.tenant_id:
        enabled_modules = user.tenant.enabled_modules.filter(is_active=True).values_list(
            "code", flat=True
        )
        assignment_qs = assignment_qs.filter(permission__module__code__in=enabled_modules)

    direct_permissions = list(assignment_qs.values("permission__code", "is_allowed"))

    return {
        "user": PermissionSubjectSerializer(user).data,
        "direct_permissions": [
            {"code": row["permission__code"], "is_allowed": row["is_allowed"]}
            for row in direct_permissions
        ],
        "effective_permissions": sorted(get_effective_permission_codes(user, refresh=True)),
    }
