from contextlib import nullcontext
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
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
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from .models import BranchProfile, UserModel, Note, BusinessProfile, SubscriptionPlan
from django.db.models import Count
from django_tenants.utils import schema_context, tenant_context
from tenancy.models import Client as Tenant, Domain
from tenancy.serializers import ClientSummarySerializer
from tenancy.utils import normalize_domain, normalize_schema_name
from .branching import ensure_main_branch_profile
from .branching import is_branch_admin, is_main_tenant_admin
from .serializers import (
    BranchProfileSerializer,
    BranchProfileSummarySerializer,
    UserBranchAssignmentSerializer,
    LoginSerializer,
    NoteSerializer,
    SubscriptionPlanSerializer,
    TenantSerializer,
    TenantSummarySerializer,
    UserCreateSerializer,
    ChangePasswordSerializer,
    TenantChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    BusinessProfileSerializer,
    BusinessProfileLanguageSerializer,
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


PASSWORD_RESET_RESPONSE_MESSAGE = (
    "If the account exists, password reset instructions have been sent."
)


def _first_error_from_dict(errors):
    for value in errors.values():
        if isinstance(value, dict):
            nested_message = _first_error_from_dict(value)
            if nested_message:
                return nested_message
        elif isinstance(value, (list, tuple)):
            if value:
                return value[0]
        elif value:
            return value
    return None


def _first_serializer_error(serializer, default="Invalid request."):
    for errors in serializer.errors.values():
        if isinstance(errors, dict):
            nested_message = _first_error_from_dict(errors)
            if nested_message:
                return nested_message
        elif isinstance(errors, (list, tuple)):
            if errors:
                return errors[0]
        elif errors:
            return errors
    return default


def _request_tenant(request):
    tenant = getattr(request, "tenant", None)
    if tenant is not None and getattr(tenant, "schema_name", "public") != "public":
        return tenant
    return None


def _password_reset_tenant_queryset():
    return Tenant.objects.select_related("subscription_plan").prefetch_related(
        "enabled_modules"
    )


def _resolve_password_reset_tenant(request, data):
    tenant = _request_tenant(request)
    if tenant is not None:
        return tenant

    tenant_id = data.get("tenant_id")
    domain = str(data.get("domain") or "").strip()
    schema_name = str(data.get("schema_name") or "").strip()
    identifier = str(data.get("tenant") or "").strip()

    if not any([tenant_id, domain, schema_name, identifier]):
        return None

    with schema_context("public"):
        if tenant_id:
            return _password_reset_tenant_queryset().get(id=tenant_id)
        if domain:
            tenant_domain = Domain.objects.select_related("tenant").get(
                domain=normalize_domain(domain)
            )
            return tenant_domain.tenant
        if schema_name:
            return _password_reset_tenant_queryset().get(
                schema_name=normalize_schema_name(schema_name)
            )
        if "." in identifier or ":" in identifier or "/" in identifier:
            tenant_domain = Domain.objects.select_related("tenant").get(
                domain=normalize_domain(identifier)
            )
            return tenant_domain.tenant
        return _password_reset_tenant_queryset().get(
            schema_name=normalize_schema_name(identifier)
        )


def _user_schema_context(tenant):
    if tenant is None:
        return nullcontext()
    return tenant_context(tenant)


def _password_reset_user_queryset(data):
    queryset = UserModel._default_manager.filter(is_active=True)
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip()
    identifier = str(data.get("identifier") or "").strip()

    if username:
        queryset = queryset.filter(username__iexact=username)
    if email:
        queryset = queryset.filter(email__iexact=email)
    if identifier:
        if "@" in identifier:
            queryset = queryset.filter(email__iexact=identifier)
        else:
            queryset = queryset.filter(username__iexact=identifier)

    return [user for user in queryset if user.has_usable_password()]


def _build_password_reset_url(tenant, uid, token):
    base_url = str(getattr(settings, "PASSWORD_RESET_FRONTEND_URL", "") or "").strip()
    if not base_url:
        return ""

    query = {"uid": uid, "token": token}
    if tenant is not None:
        query["tenant"] = tenant.schema_name
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(query)}"


def _send_password_reset_email(user, tenant, uid, token):
    if not user.email:
        return

    reset_url = _build_password_reset_url(tenant, uid, token)
    tenant_label = f"\nTenant: {tenant.schema_name}" if tenant is not None else ""
    reset_details = reset_url or f"UID: {uid}\nToken: {token}"
    message = (
        f"Hello {user.get_username()},\n\n"
        "We received a request to reset your password."
        f"{tenant_label}\n\n"
        f"Use the link or reset details below to set a new password:\n{reset_details}\n\n"
        "If you did not request this, you can ignore this email."
    )
    send_mail(
        subject="Reset your password",
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[user.email],
        fail_silently=True,
    )


def _decode_password_reset_uid(uid):
    try:
        return force_str(urlsafe_base64_decode(uid))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        return None


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

        if (
            tenant is not None
            and getattr(connection, "schema_name", "public") != "public"
            and user.is_staff
            and (
                user.branch_role == UserModel.BRANCH_ROLE_MAIN_ADMIN
                or user.branch_profile_id is None
            )
        ):
            ensure_main_branch_profile(tenant=tenant, admin_user=user)

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
            "branch_role": user.branch_role,
            "is_main_tenant_admin": is_main_tenant_admin(user),
            "is_branch_admin": is_branch_admin(user),
            "branch_profile": BranchProfileSummarySerializer(user.branch_profile).data
            if getattr(user, "branch_profile", None)
            else None,
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
            return bool(is_main_tenant_admin(user) or is_branch_admin(user))

        return bool(
            user.is_superuser
            or (is_main_tenant_admin(user) and getattr(user, "tenant_id", None))
        )

    def get_queryset(self):
        queryset = UserModel.objects.all()
        request_tenant = getattr(self.request, "tenant", None)
        if (
            request_tenant is not None
            and getattr(request_tenant, "schema_name", "public") != "public"
        ):
            queryset = queryset.select_related("branch_profile").order_by("username")
            if is_main_tenant_admin(self.request.user):
                return queryset
            branch_id = getattr(self.request.user, "branch_profile_id", None)
            return queryset.filter(branch_profile_id=branch_id) if branch_id else queryset.none()
        if self.request.user.is_superuser:
            return queryset.select_related("branch_profile").order_by("username")
        if self.request.user.is_staff and self.request.user.tenant_id:
            return queryset.filter(tenant=self.request.user.tenant).select_related(
                "branch_profile"
            ).order_by("username")
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


class BranchProfileListCreateAPIView(generics.GenericAPIView):
    serializer_class = BranchProfileSerializer
    permission_classes = [IsAuthenticated]
    permission_resource = "branch_profiles"

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

    def _is_tenant_admin(self, request):
        return is_main_tenant_admin(request.user)

    def _sync_manager_branch(self, branch):
        if branch.manager_id and branch.manager.branch_profile_id != branch.id:
            branch.manager.branch_profile = branch
            branch.manager.save(update_fields=["branch_profile"])

    def get_queryset(self):
        queryset = (
            BranchProfile.objects.select_related(
                "manager",
                "created_by",
            ).annotate(users_count=Count("users"))
        )
        if self._is_tenant_admin(self.request):
            return queryset.order_by("-is_main", "city", "name")

        branch_id = getattr(self.request.user, "branch_profile_id", None)
        if branch_id:
            return queryset.filter(id=branch_id)
        return queryset.none()

    def get(self, request):
        if self._is_tenant_admin(request) and not self.get_queryset().exists():
            ensure_main_branch_profile(
                tenant=getattr(request, "tenant", None),
                admin_user=request.user,
            )

        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Branch profiles fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not self._is_tenant_admin(request):
            return Response(
                {
                    "status": False,
                    "message": "Only tenant admin can create branch profiles.",
                    "data": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = serializer.save(created_by=request.user)
        self._sync_manager_branch(branch)
        return Response(
            {
                "status": True,
                "message": "Branch profile created successfully.",
                "data": self.get_serializer(branch).data,
            },
            status=status.HTTP_201_CREATED,
        )


class BranchProfileDetailAPIView(generics.GenericAPIView):
    serializer_class = BranchProfileSerializer
    permission_classes = [IsAuthenticated]
    permission_resource = "branch_profiles"

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

    def _is_tenant_admin(self, request):
        return is_main_tenant_admin(request.user)

    def _sync_manager_branch(self, branch):
        if branch.manager_id and branch.manager.branch_profile_id != branch.id:
            branch.manager.branch_profile = branch
            branch.manager.save(update_fields=["branch_profile"])

    def get_queryset(self):
        return BranchProfile.objects.select_related(
            "manager",
            "created_by",
        ).annotate(users_count=Count("users"))

    def get_object(self, request, id):
        queryset = self.get_queryset()
        if not self._is_tenant_admin(request):
            queryset = queryset.filter(id=getattr(request.user, "branch_profile_id", None))
        return get_object_or_404(queryset, id=id)

    def get(self, request, id):
        branch = self.get_object(request, id)
        return Response(
            {
                "status": True,
                "message": "Branch profile fetched successfully.",
                "data": self.get_serializer(branch).data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, id):
        return self._update(request, id, partial=True)

    def patch(self, request, id):
        return self._update(request, id, partial=True)

    def _update(self, request, id, partial):
        if not self._is_tenant_admin(request):
            return Response(
                {
                    "status": False,
                    "message": "Only tenant admin can update branch profiles.",
                    "data": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        branch = self.get_object(request, id)
        serializer = self.get_serializer(branch, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        branch = serializer.save()
        self._sync_manager_branch(branch)
        return Response(
            {
                "status": True,
                "message": "Branch profile updated successfully.",
                "data": self.get_serializer(branch).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, id):
        if not self._is_tenant_admin(request):
            return Response(
                {
                    "status": False,
                    "message": "Only tenant admin can delete branch profiles.",
                    "data": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        branch = self.get_object(request, id)
        if branch.is_main:
            return Response(
                {
                    "status": False,
                    "message": "Main branch cannot be deleted.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if branch.users.exists():
            return Response(
                {
                    "status": False,
                    "message": "Cannot delete branch while users are assigned to it.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch.delete()
        return Response(
            {"status": True, "message": "Branch profile deleted successfully.", "data": {}},
            status=status.HTTP_200_OK,
        )


class BranchProfileUsersAPIView(generics.GenericAPIView):
    serializer_class = UserCreateSerializer
    permission_classes = [IsAuthenticated]
    permission_resource = "branch_profiles"

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

    def get_branch(self, request, id):
        queryset = BranchProfile.objects.all()
        if not is_main_tenant_admin(request.user):
            queryset = queryset.filter(id=getattr(request.user, "branch_profile_id", None))
        return get_object_or_404(queryset, id=id)

    def get(self, request, id):
        branch = self.get_branch(request, id)
        users = UserModel.objects.filter(branch_profile=branch).order_by("username")
        serializer = self.get_serializer(users, many=True)
        return Response(
            {
                "status": True,
                "message": "Branch users fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UserBranchAssignmentAPIView(generics.GenericAPIView):
    serializer_class = UserBranchAssignmentSerializer
    permission_classes = [IsAuthenticated]
    permission_resource = "branch_profiles"

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

    def get_user(self, request, id):
        if not is_main_tenant_admin(request.user):
            raise PermissionDenied("Only tenant admin can assign users to branches.")
        return get_object_or_404(
            UserModel.objects.select_related("branch_profile"),
            id=id,
        )

    def get(self, request, id):
        user = self.get_user(request, id)
        return Response(
            {
                "status": True,
                "message": "User branch fetched successfully.",
                "data": {
                    "user_id": str(user.id),
                    "username": user.username,
                    "branch_profile": BranchProfileSummarySerializer(
                        user.branch_profile
                    ).data
                    if user.branch_profile
                    else None,
                },
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, id):
        return self._update(request, id)

    def patch(self, request, id):
        return self._update(request, id)

    def _update(self, request, id):
        user = self.get_user(request, id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user.branch_profile = serializer.validated_data["branch_profile_id"]
        user.save(update_fields=["branch_profile"])
        return Response(
            {
                "status": True,
                "message": "User branch updated successfully.",
                "data": {
                    "user_id": str(user.id),
                    "username": user.username,
                    "branch_profile": BranchProfileSummarySerializer(
                        user.branch_profile
                    ).data
                    if user.branch_profile
                    else None,
                },
            },
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


class TenantChangePasswordAPIView(generics.GenericAPIView):
    serializer_class = TenantChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": _first_serializer_error(serializer, "Invalid password."),
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response(
            {
                "status": True,
                "message": "Password changed successfully.",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestAPIView(generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def _generic_response(self):
        return Response(
            {
                "status": True,
                "message": PASSWORD_RESET_RESPONSE_MESSAGE,
                "data": {},
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": _first_serializer_error(serializer),
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tenant = _resolve_password_reset_tenant(request, serializer.validated_data)
        except (Tenant.DoesNotExist, Domain.DoesNotExist, ValueError):
            return self._generic_response()

        debug_tokens = []
        with _user_schema_context(tenant):
            for user in _password_reset_user_queryset(serializer.validated_data):
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                _send_password_reset_email(user, tenant, uid, token)
                if getattr(settings, "PASSWORD_RESET_RETURN_TOKEN", False):
                    debug_tokens.append(
                        {
                            "uid": uid,
                            "token": token,
                            "tenant": tenant.schema_name if tenant is not None else None,
                        }
                    )

        data = {}
        if debug_tokens:
            data["reset_tokens"] = debug_tokens
            if len(debug_tokens) == 1:
                data.update(debug_tokens[0])

        return Response(
            {
                "status": True,
                "message": PASSWORD_RESET_RESPONSE_MESSAGE,
                "data": data,
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmAPIView(generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def _invalid_link_response(self):
        return Response(
            {
                "status": False,
                "message": "Invalid or expired password reset token.",
                "data": {},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": False,
                    "message": _first_serializer_error(serializer),
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tenant = _resolve_password_reset_tenant(request, serializer.validated_data)
        except (Tenant.DoesNotExist, Domain.DoesNotExist, ValueError):
            return self._invalid_link_response()

        user_id = _decode_password_reset_uid(serializer.validated_data["uid"])
        if user_id is None:
            return self._invalid_link_response()

        with _user_schema_context(tenant):
            try:
                user = UserModel._default_manager.get(pk=user_id, is_active=True)
            except UserModel.DoesNotExist:
                return self._invalid_link_response()

            if not default_token_generator.check_token(
                user,
                serializer.validated_data["token"],
            ):
                return self._invalid_link_response()

            password_serializer = ChangePasswordSerializer(
                data={"new_password": serializer.validated_data["new_password"]},
                context={**self.get_serializer_context(), "target_user": user},
            )
            if not password_serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": _first_serializer_error(
                            password_serializer,
                            "Invalid password.",
                        ),
                        "data": {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(password_serializer.validated_data["new_password"])
            user.save(update_fields=["password"])

        return Response(
            {
                "status": True,
                "message": "Password reset successfully.",
                "data": {},
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
        if is_self and not request.user.check_password(
            request.data.get("current_password", "")
        ):
            return Response(
                {
                    "status": False,
                    "message": "Current password is incorrect.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
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


class BusinessProfileLanguageAPIView(generics.GenericAPIView):
    serializer_class = BusinessProfileLanguageSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def dispatch(self, request, *args, **kwargs):
        guard = _tenant_only_guard()
        if guard is not None:
            return guard
        return super().dispatch(request, *args, **kwargs)

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [permission() for permission in self.permission_classes]

    def get_profile(self):
        return BusinessProfile.objects.order_by("id").first()

    def get(self, request):
        profile = self.get_profile()
        selected_language = (
            profile.selected_language
            if profile
            else BusinessProfile.LANGUAGE_ENGLISH
        )
        return Response(
            {
                "status": True,
                "message": "Business language fetched successfully.",
                "data": {"selected_language": selected_language},
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            error_messages = []
            for field, errors in serializer.errors.items():
                error_messages.extend(errors)
            return Response(
                {"status": False, "message": error_messages[0], "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = self.get_profile()
        if not profile:
            return Response(
                {
                    "status": False,
                    "message": "Business profile not found.",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

        profile.selected_language = serializer.validated_data["selected_language"]
        profile.save(update_fields=["selected_language", "updated_at"])
        return Response(
            {
                "status": True,
                "message": "Business language updated successfully.",
                "data": {"selected_language": profile.selected_language},
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        return self.put(request)


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
