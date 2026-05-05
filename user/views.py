from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth import authenticate
from django.db import connection
from django.http import JsonResponse
from .models import UserModel, Note, BusinessProfile, SubscriptionPlan
from django_tenants.utils import schema_context, tenant_context
from tenancy.models import Client as Tenant, Domain
from tenancy.serializers import ClientSummarySerializer
from tenancy.utils import normalize_domain, normalize_schema_name
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
from radha.Utils.permissions import (
    IsAdminUserOrReadOnly,
    get_effective_permission_codes,
    user_has_permission,
)
from user.tenanting import provision_tenant_schema


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        tenant = getattr(request, "tenant", None)
        is_public = tenant is None or getattr(tenant, "schema_name", "public") == "public"
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
            and is_public
        )

# --------------------    LoginViewSet    --------------------


class LoginViewSet(generics.GenericAPIView):
    """
    User Login ViewSet
    """

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def _get_request_tenant(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None and getattr(tenant, "schema_name", "public") == "public":
            return None
        return tenant

    def _tenant_queryset(self):
        return Tenant.objects.select_related("subscription_plan").prefetch_related(
            "enabled_modules"
        )

    def _attach_tenant_domain(self, tenant):
        if getattr(tenant, "domain_url", None):
            return tenant

        domain = tenant.get_primary_domain()
        tenant.domain_url = domain.domain if domain else ""
        return tenant

    def _resolve_tenant_by_schema(self, schema_name):
        schema_name = normalize_schema_name(schema_name)
        with schema_context("public"):
            return self._attach_tenant_domain(
                self._tenant_queryset().get(schema_name=schema_name)
            )

    def _resolve_tenant_by_domain(self, domain):
        domain = normalize_domain(domain)
        with schema_context("public"):
            tenant_domain = Domain.objects.select_related(
                "tenant",
                "tenant__subscription_plan",
            ).get(domain=domain)
            return self._attach_tenant_domain(tenant_domain.tenant)

    def _resolve_requested_tenant(self, data):
        tenant_id = data.get("tenant_id")
        if tenant_id:
            with schema_context("public"):
                return self._attach_tenant_domain(
                    self._tenant_queryset().get(id=tenant_id)
                )

        if data.get("domain"):
            return self._resolve_tenant_by_domain(data["domain"])

        if data.get("schema_name"):
            return self._resolve_tenant_by_schema(data["schema_name"])

        identifier = str(data.get("tenant") or "").strip()
        if not identifier:
            return None

        if "." in identifier or ":" in identifier or "/" in identifier:
            return self._resolve_tenant_by_domain(identifier)
        return self._resolve_tenant_by_schema(identifier)

    def _restore_request_tenant(self, request, previous_tenant):
        if previous_tenant is None:
            if hasattr(request, "tenant"):
                delattr(request, "tenant")
            return
        request.tenant = previous_tenant

    def _login_response(self, user, tenant):
        if tenant is not None:
            user._active_tenant = tenant

        if tenant is not None and not tenant.has_active_subscription:
            return Response(
                {
                    "status": False,
                    "message": "Tenant subscription is not active.",
                    "data": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user_type = "admin" if user.is_superuser or user.is_staff else "user"
        if getattr(connection, "schema_name", "public") != "public":
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
                ClientSummarySerializer(tenant).data
                if tenant is not None
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

    def _authenticate_for_tenant(self, request, tenant, username, password):
        previous_tenant = getattr(request, "tenant", None)
        try:
            request.tenant = tenant
            with tenant_context(tenant):
                user = authenticate(request, username=username, password=password)
                if not user:
                    return None
                return self._login_response(user, tenant)
        finally:
            self._restore_request_tenant(request, previous_tenant)

    def _tenant_credentials_match(self, request, tenant, username, password):
        previous_tenant = getattr(request, "tenant", None)
        try:
            request.tenant = tenant
            with tenant_context(tenant):
                return bool(
                    authenticate(request, username=username, password=password)
                )
        finally:
            self._restore_request_tenant(request, previous_tenant)

    def _find_matching_tenants(self, request, username, password):
        matches = []
        with schema_context("public"):
            tenants = list(
                self._tenant_queryset().exclude(schema_name="public").order_by("name")
            )

        for tenant in tenants:
            self._attach_tenant_domain(tenant)
            if self._tenant_credentials_match(request, tenant, username, password):
                matches.append(tenant)
                if len(matches) > 1:
                    break
        return matches

    def _invalid_login_response(self):
        return Response(
            {
                "status": False,
                "message": "Invalid username or password.",
                "data": {},
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            error_messages = []
            for field, errors in serializer.errors.items():
                error_messages.extend(errors)
            return Response(
                {
                    "status": False,
                    "message": error_messages[0],
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        try:
            requested_tenant = self._resolve_requested_tenant(serializer.validated_data)
        except (Tenant.DoesNotExist, Domain.DoesNotExist, ValueError):
            return Response(
                {
                    "status": False,
                    "message": "Tenant not found.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if requested_tenant is not None:
            response = self._authenticate_for_tenant(
                request,
                requested_tenant,
                username,
                password,
            )
            return response or self._invalid_login_response()

        user = authenticate(request, username=username, password=password)
        if user:
            return self._login_response(user, self._get_request_tenant(request))

        if self._get_request_tenant(request) is None:
            matching_tenants = self._find_matching_tenants(request, username, password)
            if len(matching_tenants) == 1:
                response = self._authenticate_for_tenant(
                    request,
                    matching_tenants[0],
                    username,
                    password,
                )
                if response is not None:
                    return response
            if len(matching_tenants) > 1:
                return Response(
                    {
                        "status": False,
                        "message": (
                            "Multiple tenants match these credentials. "
                            "Please include tenant, schema_name, or domain."
                        ),
                        "data": {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return self._invalid_login_response()


class TenantTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_scope = "token_refresh"


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
        request_tenant = getattr(self.request, "tenant", None)
        if (
            request_tenant is not None
            and getattr(request_tenant, "schema_name", "public") != "public"
        ):
            return bool(user.is_staff)

        return bool(
            user.is_superuser
            or (user.is_staff and getattr(user, "tenant_id", None))
        )

    def get_queryset(self):
        queryset = UserModel.objects.all()
        request_tenant = getattr(self.request, "tenant", None)
        if (
            request_tenant is not None
            and getattr(request_tenant, "schema_name", "public") != "public"
        ):
            return queryset.order_by("username")
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
        # 1. Resolve target first so authorization decisions know who we're acting on.
        try:
            target_user = UserModel.objects.get(id=id)
        except UserModel.DoesNotExist:
            return Response(
                {"status": False, "message": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        is_self = str(request.user.id) == str(target_user.id)
        is_superuser = bool(request.user.is_superuser)
        has_manage_password_permission = user_has_permission(
            request.user, "users.change_password"
        )

        request_tenant = getattr(request, "tenant", None)
        on_tenant_schema = (
            request_tenant is not None
            and getattr(request_tenant, "schema_name", "public") != "public"
        )
        if on_tenant_schema:
            same_tenant = True
        else:
            actor_tenant_id = getattr(request.user, "tenant_id", None)
            target_tenant_id = getattr(target_user, "tenant_id", None)
            same_tenant = (
                actor_tenant_id == target_tenant_id
                if actor_tenant_id or target_tenant_id
                else True
            )

        allowed = (
            is_self
            or is_superuser
            or (has_manage_password_permission and same_tenant)
            or (request.user.is_staff and same_tenant)
        )
        if not allowed:
            return Response(
                {"status": False, "message": "You do not have permission to change this password."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "target_user": target_user},
        )
        if not serializer.is_valid():
            error_messages = []
            for field, errors in serializer.errors.items():
                error_messages.extend(errors)
            return Response(
                {
                    "status": False,
                    "message": error_messages[0] if error_messages else "Invalid password.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_user.set_password(serializer.validated_data["new_password"])
        target_user.save()

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


def _tenant_only_guard():
    if getattr(connection, "schema_name", "public") == "public":
        return JsonResponse(
            {
                "status": False,
                "message": "Business profiles are available only on tenant domains.",
                "data": {},
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    return None


class BusinessProfileAPIView(generics.GenericAPIView):
    serializer_class = BusinessProfileSerializer
    queryset = BusinessProfile.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "business_profiles"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

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

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

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
