# permissions.py
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS

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
            
        # Allow GET, HEAD, OPTIONS requests for authenticated users
        if request.method in SAFE_METHODS:
            return True
            
        # Require admin for all other methods
        return request.user.is_staff


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
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Allow GET, HEAD, OPTIONS requests for authenticated users
        if request.method in SAFE_METHODS:
            return True
            
        # Allow if admin
        if request.user.is_staff:
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