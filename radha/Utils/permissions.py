# permissions.py
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS

try:
    from django_tenants.utils import schema_context
except Exception:  # pragma: no cover
    schema_context = None


HTTP_METHOD_PERMISSION_MAP = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def normalize_permission_codes(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [item for item in value if item]


def get_required_permission_codes(request, view):
    permission_action_map = getattr(view, "permission_action_map", {})
    view_action = getattr(view, "action", None)

    if view_action and view_action in permission_action_map:
        return normalize_permission_codes(permission_action_map[view_action])

    if request.method in permission_action_map:
        return normalize_permission_codes(permission_action_map[request.method])

    resource = getattr(view, "permission_resource", None)
    permission_action = getattr(view, "permission_action", None)

    if not resource:
        return []

    action = permission_action or HTTP_METHOD_PERMISSION_MAP.get(request.method)
    if not action:
        return []

    return [f"{resource}.{action}"]


def get_effective_permission_codes(user, refresh=False):
    if not getattr(user, "is_authenticated", False):
        return set()

    if user.is_superuser:
        return {"*"}

    if not refresh and hasattr(user, "_effective_permission_codes_cache"):
        return user._effective_permission_codes_cache

    from accesscontrol.models import AccessPermission, UserPermissionAssignment

    tenant = get_user_active_tenant(user)
    if tenant and not tenant.has_active_subscription:
        user._effective_permission_codes_cache = set()
        return set()

    tenant_module_codes = get_tenant_enabled_module_codes(user, refresh=refresh)

    if user.is_staff and tenant:
        if not tenant_module_codes:
            user._effective_permission_codes_cache = set()
            return set()

        effective_codes = set(
            AccessPermission.objects.filter(
                is_active=True,
                module__is_active=True,
                module__code__in=tenant_module_codes,
            ).values_list("code", flat=True)
        )
        user._effective_permission_codes_cache = effective_codes
        return effective_codes

    allowed_codes = set()
    denied_codes = set()
    assignments = UserPermissionAssignment.objects.filter(
        user=user,
        permission__is_active=True,
    ).select_related("permission", "permission__module")

    if tenant:
        if not tenant_module_codes:
            user._effective_permission_codes_cache = set()
            return set()
        assignments = assignments.filter(permission__module__code__in=tenant_module_codes)

    for assignment in assignments.all():
        if assignment.is_allowed:
            allowed_codes.add(assignment.permission.code)
        else:
            denied_codes.add(assignment.permission.code)

    effective_codes = allowed_codes - denied_codes
    user._effective_permission_codes_cache = effective_codes
    return effective_codes


def user_has_permission(user, permission_code):
    if not getattr(user, "is_authenticated", False):
        return False
    effective_codes = get_effective_permission_codes(user)
    return "*" in effective_codes or permission_code in effective_codes


def get_tenant_enabled_module_codes(user, refresh=False):
    tenant = get_user_active_tenant(user)
    if tenant is None:
        return None

    if not refresh and hasattr(user, "_tenant_enabled_module_codes_cache"):
        return user._tenant_enabled_module_codes_cache

    if schema_context is None:
        module_codes = set(
            tenant.enabled_modules.filter(is_active=True).values_list("code", flat=True)
        )
    else:
        with schema_context("public"):
            module_codes = set(
                tenant.enabled_modules.filter(is_active=True).values_list(
                    "code",
                    flat=True,
                )
            )
    user._tenant_enabled_module_codes_cache = module_codes
    return module_codes


def tenant_subscription_allows_access(user):
    tenant = get_user_active_tenant(user)
    return tenant is None or tenant.has_active_subscription


def tenant_can_use_permissions(user, permission_codes):
    tenant = get_user_active_tenant(user)
    if tenant is None:
        return True
    if not tenant.has_active_subscription:
        return False

    normalized_codes = normalize_permission_codes(permission_codes)
    if not normalized_codes:
        return True

    enabled_modules = get_tenant_enabled_module_codes(user)
    if not enabled_modules:
        return False

    return all(
        "." in code and code.split(".", 1)[0] in enabled_modules
        for code in normalized_codes
    )


class IsAdminUserOrReadOnly(IsAuthenticated):
    """
    Custom permission class to allow:
    - Read-only access for authenticated users
    - Full access for admin users
    
    Usage:
    permission_classes = [IsAdminUserOrReadOnly]
    """
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        
        if not is_authenticated:
            return False

        if not tenant_subscription_allows_access(request.user):
            return False

        required_codes = get_required_permission_codes(request, view)

        if request.method in SAFE_METHODS and not required_codes:
            return True

        if request.user.is_superuser:
            return True

        if request.user.is_staff:
            return tenant_can_use_permissions(request.user, required_codes)

        if required_codes:
            return all(user_has_permission(request.user, code) for code in required_codes)

        return False


def get_user_active_tenant(user):
    tenant = getattr(user, "_active_tenant", None)
    if tenant is not None:
        return tenant
    return getattr(user, "tenant", None)


class IsOwnerOrAdmin(BasePermission):
    """
    Custom permission class to allow:
    - Read-only access for authenticated users
    - Full access for admin users
    - Full access for object owners
    
    Usage:
    1. Add permission_classes = [IsOwnerOrAdmin]
    2. Add user field in your model: user = models.ForeignKey(User, on_delete=models.CASCADE)
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        if not tenant_subscription_allows_access(request.user):
            return False

        required_codes = get_required_permission_codes(request, view)

        if request.user.is_superuser:
            return True

        if request.user.is_staff:
            return tenant_can_use_permissions(request.user, required_codes)

        if required_codes:
            return all(user_has_permission(request.user, code) for code in required_codes)

        return True

    def has_object_permission(self, request, view, obj):
        # Allow GET, HEAD, OPTIONS requests for authenticated users
        if request.method in SAFE_METHODS:
            return True
            
        # Allow if admin
        if request.user.is_superuser:
            return True

        required_codes = get_required_permission_codes(request, view)
        if request.user.is_staff:
            return tenant_can_use_permissions(request.user, required_codes)

        if required_codes and all(
            user_has_permission(request.user, code) for code in required_codes
        ):
            return True
            
        # Allow if owner
        return hasattr(obj, 'user') and obj.user == request.user
