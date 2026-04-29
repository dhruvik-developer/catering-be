from django.shortcuts import get_object_or_404
from django.db import connection
from rest_framework import generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from tenancy.models import Client, SubscriptionPlan
from tenancy.serializers import (
    ClientSerializer,
    ClientSummarySerializer,
    SubscriptionPlanSerializer,
)


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
            and getattr(connection, "schema_name", "public") == "public"
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
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        return Response(
            {
                "status": True,
                "message": "Subscription plan created successfully.",
                "data": self.get_serializer(plan).data,
            },
            status=status.HTTP_201_CREATED,
        )


class SubscriptionPlanDetailAPIView(generics.GenericAPIView):
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()
    permission_classes = [IsPlatformAdmin]

    def get_object(self, id):
        return get_object_or_404(self.get_queryset(), id=id)

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
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        return Response(
            {
                "status": True,
                "message": "Subscription plan updated successfully.",
                "data": self.get_serializer(plan).data,
            },
            status=status.HTTP_200_OK,
        )


class ClientListCreateAPIView(generics.GenericAPIView):
    serializer_class = ClientSerializer
    queryset = Client.objects.prefetch_related("enabled_modules", "domains")
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
        serializer.is_valid(raise_exception=True)
        client = serializer.save()
        return Response(
            {
                "status": True,
                "message": "Tenant created successfully.",
                "data": self.get_serializer(client).data,
            },
            status=status.HTTP_200_OK,
        )


class ClientDetailAPIView(generics.GenericAPIView):
    serializer_class = ClientSerializer
    queryset = Client.objects.prefetch_related("enabled_modules", "domains")
    permission_classes = [IsPlatformAdmin]

    def get_object(self, id):
        return get_object_or_404(self.get_queryset(), id=id)

    def get(self, request, id):
        client = self.get_object(id)
        return Response(
            {
                "status": True,
                "message": "Tenant fetched successfully.",
                "data": self.get_serializer(client).data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, id):
        client = self.get_object(id)
        serializer = self.get_serializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        client = serializer.save()
        return Response(
            {
                "status": True,
                "message": "Tenant updated successfully.",
                "data": self.get_serializer(client).data,
            },
            status=status.HTTP_200_OK,
        )


class TenantProvisionAPIView(generics.GenericAPIView):
    queryset = Client.objects.all()
    permission_classes = [IsPlatformAdmin]

    def post(self, request, id):
        client = get_object_or_404(self.get_queryset(), id=id)
        client.create_schema(check_if_exists=True, sync_schema=True)
        return Response(
            {
                "status": True,
                "message": "Tenant schema provisioned successfully.",
                "data": ClientSummarySerializer(client).data,
            },
            status=status.HTTP_200_OK,
        )


class MyTenantAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClientSummarySerializer

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
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
