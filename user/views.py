from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import authenticate
from .models import UserModel, Note, BusinessProfile, SubscriptionPlan, Tenant
from .serializers import (
    LoginSerializer,
    NoteSerializer,
    SubscriptionPlanSerializer,
    TenantSerializer,
    TenantSummarySerializer,
    UserCreateSerializer,
    ChangePasswordSerializer,
    BusinessProfileSerializer,
)
from django.shortcuts import get_object_or_404
from radha.Utils.permissions import IsAdminUserOrReadOnly, user_has_permission, get_effective_permission_codes
from user.tenanting import provision_tenant_schema


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )

# --------------------    LoginViewSet    --------------------


class LoginViewSet(generics.GenericAPIView):
    """
    User Login ViewSet
    """

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            if user.tenant and not user.tenant.has_active_subscription:
                return Response(
                    {
                        "status": False,
                        "message": "Tenant subscription is not active.",
                        "data": {},
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            user_type = "admin" if user.is_superuser or user.is_staff else "user"
            if hasattr(user, "staff_profile"):
                user_type = "staff"
            elif hasattr(user, "vendor_profile"):
                user_type = "vendor"

            response_data = {
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "user_type": user_type,
                "permissions": sorted(get_effective_permission_codes(user)),
                "tenant": (
                    TenantSummarySerializer(user.tenant).data
                    if user.tenant_id
                    else None
                ),
                "tokens": user.tokens,
            }
            return Response(
                {
                    "status": True,
                    "message": "Login successfully",
                    "data": response_data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "status": False,
                "message": "Invalid username or password.",
                "data": {},
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )


class NoteViewSet(generics.GenericAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "notes"

    def post(self, request):

        serializer = NoteSerializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            serializer.save()

            return Response(
                {"status": True, "message": "Note Store successfully", "data": {}},
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "status": False,
                "message": "Something went wrong",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):

        get_note = Note.objects.filter(id=pk).first()
        if not get_note:
            return Response(
                {
                    "status": False,
                    "message": "Note not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

        serializer = NoteSerializer(get_note, data=request.data, partial=True)

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Note updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": False,
                "message": "Something went wrong",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request):
        queryset = Note.objects.all()
        serializer = NoteSerializer(queryset, many=True)
        return Response(
            {
                "status": True,
                "message": "Note list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UserCreateAPIView(generics.GenericAPIView):
    serializer_class = UserCreateSerializer
    queryset = UserModel.objects.all()
    permission_classes = [IsAuthenticated]
    permission_resource = "users"

    def _can_manage_users(self, user):
        return bool(
            user.is_superuser
            or (user.is_staff and getattr(user, "tenant_id", None))
        )

    def get_queryset(self):
        queryset = UserModel.objects.select_related("tenant").all()
        if self.request.user.is_superuser:
            return queryset.order_by("username")
        if self.request.user.is_staff and self.request.user.tenant_id:
            return queryset.filter(tenant=self.request.user.tenant).order_by("username")
        return queryset.none()

    def post(self, request):
        if not self._can_manage_users(request.user):
            raise PermissionDenied("Only platform admin or tenant admin can create this resource.")

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "User created successfully",
                    "data": self.get_serializer(user).data,
                },
                status=status.HTTP_200_OK,
            )
        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]}, status=status.HTTP_200_OK
        )

    def get(self, request):
        users = self.get_queryset()
        serializer = self.get_serializer(users, many=True)
        return Response(
            {
                "status": True,
                "message": "User list fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, id):
        user = get_object_or_404(self.get_queryset(), id=id)
        user.delete()
        return Response(
            {"status": True, "message": "User deleted successfully."},
            status=status.HTTP_200_OK,
        )


class SubscriptionPlanListCreateAPIView(generics.GenericAPIView):
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Subscription plans fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            plan = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Subscription plan created successfully.",
                    "data": self.get_serializer(plan).data,
                },
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


class SubscriptionPlanDetailAPIView(generics.GenericAPIView):
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()
    permission_classes = [IsPlatformAdmin]

    def get_object(self, id):
        return get_object_or_404(SubscriptionPlan, id=id)

    def get(self, request, id):
        plan = self.get_object(id)
        return Response(
            {
                "status": True,
                "message": "Subscription plan fetched successfully.",
                "data": self.get_serializer(plan).data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, id):
        plan = self.get_object(id)
        serializer = self.get_serializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            plan = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Subscription plan updated successfully.",
                    "data": self.get_serializer(plan).data,
                },
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


class TenantListCreateAPIView(generics.GenericAPIView):
    serializer_class = TenantSerializer
    queryset = Tenant.objects.select_related("subscription_plan", "created_by").prefetch_related(
        "enabled_modules"
    )
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Tenants fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                tenant = serializer.save()
            except Exception as exc:
                return Response(
                    {
                        "status": False,
                        "message": f"Tenant schema provisioning failed: {exc}",
                        "data": {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {
                    "status": True,
                    "message": "Tenant created successfully.",
                    "data": self.get_serializer(tenant).data,
                },
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


class TenantDetailAPIView(generics.GenericAPIView):
    serializer_class = TenantSerializer
    queryset = Tenant.objects.select_related("subscription_plan", "created_by").prefetch_related(
        "enabled_modules"
    )
    permission_classes = [IsPlatformAdmin]

    def get_object(self, id):
        return get_object_or_404(self.get_queryset(), id=id)

    def get(self, request, id):
        tenant = self.get_object(id)
        return Response(
            {
                "status": True,
                "message": "Tenant fetched successfully.",
                "data": self.get_serializer(tenant).data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, id):
        tenant = self.get_object(id)
        serializer = self.get_serializer(tenant, data=request.data, partial=True)
        if serializer.is_valid():
            tenant = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Tenant updated successfully.",
                    "data": self.get_serializer(tenant).data,
                },
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]},
            status=status.HTTP_400_BAD_REQUEST,
        )


class TenantProvisionAPIView(generics.GenericAPIView):
    queryset = Tenant.objects.all()
    permission_classes = [IsPlatformAdmin]

    def post(self, request, id):
        tenant = get_object_or_404(Tenant, id=id)
        try:
            provision_tenant_schema(tenant)
        except Exception as exc:
            return Response(
                {
                    "status": False,
                    "message": f"Tenant schema provisioning failed: {exc}",
                    "data": TenantSummarySerializer(tenant).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant.refresh_from_db()
        return Response(
            {
                "status": True,
                "message": "Tenant schema provisioned successfully.",
                "data": TenantSummarySerializer(tenant).data,
            },
            status=status.HTTP_200_OK,
        )


class MyTenantAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TenantSummarySerializer

    def get(self, request):
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if tenant is None:
            return Response(
                {
                    "status": True,
                    "message": "No tenant assigned.",
                    "data": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": True,
                "message": "Tenant fetched successfully.",
                "data": self.get_serializer(tenant).data,
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordAPIView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        has_manage_password_permission = user_has_permission(
            request.user, "users.change_password"
        )
        if (
            not request.user.is_staff
            and not has_manage_password_permission
            and str(request.user.id) != str(id)
        ):
            return Response(
                {"status": False, "message": "You do not have permission to change this password."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                user = UserModel.objects.get(id=id)
            except UserModel.DoesNotExist:
                return Response(
                    {"status": False, "message": "User not found."},
                    status=status.HTTP_200_OK,
                )

            if request.user.tenant_id and user.tenant_id != request.user.tenant_id:
                return Response(
                    {
                        "status": False,
                        "message": "You cannot change password for another tenant.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            new_password = serializer.validated_data["new_password"]
            user.set_password(new_password)
            user.save()

            return Response(
                {"status": True, "message": "Password changed successfully."},
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)

        return Response(
            {"status": False, "message": error_messages[0]}, status=status.HTTP_400_BAD_REQUEST
        )


class BusinessProfileAPIView(generics.GenericAPIView):
    serializer_class = BusinessProfileSerializer
    queryset = BusinessProfile.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "business_profiles"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [permission() for permission in self.permission_classes]

    def get(self, request):
        # If you want to get all profiles:
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "status": True,
                "message": "Business profiles fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        # Typically one user has one profile, you can map it automatically if requests are authenticated:
        # data = request.data.copy()
        # data['user'] = request.user.id
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Business profile created successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]}, status=status.HTTP_200_OK
        )


class BusinessProfileDetailAPIView(generics.GenericAPIView):
    serializer_class = BusinessProfileSerializer
    queryset = BusinessProfile.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "business_profiles"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [permission() for permission in self.permission_classes]

    def get_object(self, id):
        try:
            return BusinessProfile.objects.get(id=id)
        except BusinessProfile.DoesNotExist:
            return None

    def get(self, request, id):
        profile = self.get_object(id)
        if not profile:
            return Response(
                {"status": False, "message": "Business profile not found.", "data": {}},
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(profile)
        return Response(
            {
                "status": True,
                "message": "Business profile fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, id):
        profile = self.get_object(id)
        if not profile:
            return Response(
                {"status": False, "message": "Business profile not found.", "data": {}},
                status=status.HTTP_200_OK,
            )

        serializer = self.get_serializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Business profile updated successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        error_messages = []
        for field, errors in serializer.errors.items():
            error_messages.extend(errors)
        return Response(
            {"status": False, "message": error_messages[0]}, status=status.HTTP_200_OK
        )
