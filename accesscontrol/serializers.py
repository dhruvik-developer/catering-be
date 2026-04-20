from django.contrib.auth import get_user_model
from rest_framework import serializers

from accesscontrol.models import (
    AccessPermission,
    PermissionModule,
    StaffRolePermissionAssignment,
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

        return attrs


class StaffRolePermissionWriteSerializer(serializers.Serializer):
    permission_codes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    def validate_permission_codes(self, value):
        codes = set(value)
        unknown_codes = codes - set(AccessPermission.objects.values_list("code", flat=True))
        if unknown_codes:
            raise serializers.ValidationError(
                f"Unknown permission codes: {', '.join(sorted(unknown_codes))}"
            )
        return list(codes)


class UserPermissionAssignmentDetailSerializer(serializers.Serializer):
    user = PermissionSubjectSerializer(read_only=True)
    role_permissions = serializers.ListField(child=serializers.CharField(), read_only=True)
    direct_permissions = serializers.ListField(child=serializers.DictField(), read_only=True)
    effective_permissions = serializers.ListField(child=serializers.CharField(), read_only=True)


class StaffRolePermissionDetailSerializer(serializers.Serializer):
    role_id = serializers.IntegerField(read_only=True)
    role_name = serializers.CharField(read_only=True)
    permission_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


def build_user_permission_payload(user):
    role_permissions = []
    if hasattr(user, "staff_profile") and user.staff_profile.role_id:
        role_permissions = list(
            StaffRolePermissionAssignment.objects.filter(role=user.staff_profile.role)
            .select_related("permission")
            .values_list("permission__code", flat=True)
        )

    direct_permissions = list(
        UserPermissionAssignment.objects.filter(user=user)
        .select_related("permission")
        .values("permission__code", "is_allowed")
    )

    return {
        "user": PermissionSubjectSerializer(user).data,
        "role_permissions": sorted(role_permissions),
        "direct_permissions": [
            {"code": row["permission__code"], "is_allowed": row["is_allowed"]}
            for row in direct_permissions
        ],
        "effective_permissions": sorted(get_effective_permission_codes(user, refresh=True)),
    }
