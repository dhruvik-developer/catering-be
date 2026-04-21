from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from accesscontrol.models import AccessPermission, PermissionModule
from accesscontrol.serializers import (
    PermissionModuleSerializer,
    PermissionSubjectSerializer,
    UserPermissionAssignmentWriteSerializer,
    build_user_permission_payload,
)
from radha.Utils.permissions import get_effective_permission_codes


UserModel = get_user_model()


class PermissionModuleListAPIView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PermissionModuleSerializer
    queryset = PermissionModule.objects.prefetch_related("permissions").filter(
        is_active=True,
        permissions__is_active=True,
    ).distinct()

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Permission modules fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class PermissionSubjectListAPIView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PermissionSubjectSerializer

    def get_queryset(self):
        queryset = (
            UserModel.objects.select_related("staff_profile__role", "vendor_profile")
            .filter(is_superuser=False)
            .order_by("username")
        )
        user_type = self.request.query_params.get("user_type")

        if user_type == "staff":
            return queryset.filter(staff_profile__isnull=False)
        if user_type == "vendor":
            return queryset.filter(vendor_profile__isnull=False)
        if user_type == "admin":
            return queryset.filter(is_staff=True)
        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Permission subjects fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UserPermissionAssignmentAPIView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserPermissionAssignmentWriteSerializer

    def get_user(self, user_id):
        return get_object_or_404(
            UserModel.objects.select_related("staff_profile__role", "vendor_profile"),
            id=user_id,
        )

    def get(self, request, user_id):
        user = self.get_user(user_id)
        return Response(
            {
                "status": True,
                "message": "User permissions fetched successfully.",
                "data": build_user_permission_payload(user),
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, user_id):
        user = self.get_user(user_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        allowed_codes = set(serializer.validated_data.get("allowed_permissions", []))
        denied_codes = set(serializer.validated_data.get("denied_permissions", []))
        requested_codes = allowed_codes | denied_codes

        user.permission_assignments.all().delete()
        permissions = {
            permission.code: permission
            for permission in AccessPermission.objects.filter(code__in=requested_codes)
        }

        for code in allowed_codes:
            user.permission_assignments.create(
                permission=permissions[code],
                is_allowed=True,
            )

        for code in denied_codes:
            user.permission_assignments.create(
                permission=permissions[code],
                is_allowed=False,
            )

        return Response(
            {
                "status": True,
                "message": "User permissions updated successfully.",
                "data": build_user_permission_payload(user),
            },
            status=status.HTTP_200_OK,
        )


class MyPermissionAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "status": True,
                "message": "Permissions fetched successfully.",
                "data": {
                    "user_id": str(request.user.id),
                    "username": request.user.username,
                    "permissions": sorted(get_effective_permission_codes(request.user)),
                },
            },
            status=status.HTTP_200_OK,
        )
