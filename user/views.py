from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import authenticate
from .models import UserModel, Note, BusinessProfile
from .serializers import (
    LoginSerializer,
    NoteSerializer,
    UserCreateSerializer,
    ChangePasswordSerializer,
    BusinessProfileSerializer,
)
from django.shortcuts import get_object_or_404
from radha.Utils.permissions import IsAdminUserOrReadOnly, user_has_permission, get_effective_permission_codes

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
            status=status.HTTP_400_BAD_REQUEST,
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
                status=status.HTTP_404_NOT_FOUND,
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
            status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request):
        queryset = Note.objects.all().order_by("title", "id")
        page = self.paginate_queryset(queryset)
        queryset = page if page is not None else queryset
        serializer = NoteSerializer(queryset, many=True)
        if page is not None:
            self.paginator.message = "Note list"
            return self.get_paginated_response(serializer.data)

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
    queryset = UserModel.objects.all().order_by("username")
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "users"

    def post(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admin can create this resource.")

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "User created successfully",
                    "data": {
                        # "id": user.id,
                        # "username": user.username,
                        # "email": user.email,
                        # "tokens": user.tokens
                    },
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

    def get(self, request):
        users = self.get_queryset()
        page = self.paginate_queryset(users)
        users = page if page is not None else users
        serializer = self.get_serializer(users, many=True)
        if page is not None:
            self.paginator.message = "User list fetched successfully."
            return self.get_paginated_response(serializer.data)

        return Response(
            {
                "status": True,
                "message": "User list fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, id):
        user = get_object_or_404(UserModel, id=id)
        user.delete()
        return Response(
            {"status": True, "message": "User deleted successfully."},
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
                    status=status.HTTP_404_NOT_FOUND,
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
    queryset = BusinessProfile.objects.all().order_by("-created_at", "id")
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
        page = self.paginate_queryset(queryset)
        queryset = page if page is not None else queryset
        serializer = self.get_serializer(queryset, many=True)
        if page is not None:
            self.paginator.message = "Business profiles fetched successfully."
            return self.get_paginated_response(serializer.data)

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
            {"status": False, "message": error_messages[0]},
            status=status.HTTP_400_BAD_REQUEST,
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
                status=status.HTTP_404_NOT_FOUND,
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
                status=status.HTTP_404_NOT_FOUND,
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
            {"status": False, "message": error_messages[0]},
            status=status.HTTP_400_BAD_REQUEST,
        )
