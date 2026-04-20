# permissions.py
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS


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

    if user.is_superuser or user.is_staff:
        return {"*"}

    if not refresh and hasattr(user, "_effective_permission_codes_cache"):
        return user._effective_permission_codes_cache

    from accesscontrol.models import StaffRolePermissionAssignment, UserPermissionAssignment

    allowed_codes = set()
    denied_codes = set()

    staff_profile = getattr(user, "staff_profile", None)
    if staff_profile and staff_profile.role_id:
        allowed_codes.update(
            StaffRolePermissionAssignment.objects.filter(
                role=staff_profile.role,
                permission__is_active=True,
            ).values_list("permission__code", flat=True)
        )

    for assignment in (
        UserPermissionAssignment.objects.filter(
            user=user,
            permission__is_active=True,
        )
        .select_related("permission")
        .all()
    ):
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

        if request.user.is_superuser or request.user.is_staff:
            return True

        required_codes = get_required_permission_codes(request, view)
        if required_codes:
            return all(user_has_permission(request.user, code) for code in required_codes)

        if request.method in SAFE_METHODS:
            return True

        return False


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

        if request.user.is_superuser or request.user.is_staff:
            return True

        required_codes = get_required_permission_codes(request, view)
        if required_codes:
            return all(user_has_permission(request.user, code) for code in required_codes)

        return True

    def has_object_permission(self, request, view, obj):
        # Allow GET, HEAD, OPTIONS requests for authenticated users
        if request.method in SAFE_METHODS:
            return True
            
        # Allow if admin
        if request.user.is_superuser or request.user.is_staff:
            return True

        required_codes = get_required_permission_codes(request, view)
        if required_codes and all(
            user_has_permission(request.user, code) for code in required_codes
        ):
            return True
            
        # Allow if owner
        return hasattr(obj, 'user') and obj.user == request.user


class IsStaffOrReadOnly(BasePermission):
    """
    Custom permission class to allow:
    - Read-only access for authenticated users
    - Full access for staff users (is_staff=True)
    
    Usage:
    permission_classes = [IsStaffOrReadOnly]
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
            
        if request.method in SAFE_METHODS:
            return True
            
        return request.user.is_staff


class GroupPermission(BasePermission):
    """
    Custom permission class to allow access based on user groups
    
    Usage:
    class YourViewSet(viewsets.ModelViewSet):
        permission_classes = [GroupPermission]
        required_groups = {
            'GET': ['view_group'],
            'POST': ['create_group'],
            'PUT': ['edit_group'],
            'DELETE': ['delete_group']
        }
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
            
        # If user is admin, allow all
        if request.user.is_staff:
            return True
            
        # Get required groups from view
        required_groups = getattr(view, 'required_groups', {})
        if not required_groups:
            return False
            
        # Get required groups for this method
        method = request.method
        if method not in required_groups:
            return False
            
        # Check if user has any of the required groups
        user_groups = request.user.groups.values_list('name', flat=True)
        return any(group in user_groups for group in required_groups[method])
