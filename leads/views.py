from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from radha.Utils.permissions import IsAdminUserOrReadOnly

from .models import Lead
from .serializers import AdminLeadSerializer, PublicLeadSerializer


class PublicContactView(APIView):
    """Unauthenticated lead submission from the public marketing website."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PublicLeadSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Thanks! We'll be in touch shortly.",
                    "data": {"id": serializer.instance.id},
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "status": False,
                "message": "Please correct the errors and try again.",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


def _parse_int(value, default, *, minimum=1, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if result < minimum:
        return minimum
    if maximum is not None and result > maximum:
        return maximum
    return result


VALID_ORDERING = {
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "full_name",
    "-full_name",
    "status",
    "-status",
}


class AdminLeadListView(generics.GenericAPIView):
    """Admin list endpoint with search, status filter, sort, pagination."""

    serializer_class = AdminLeadSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "leads"

    def get(self, request):
        queryset = Lead.objects.all()

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(company__icontains=search)
            )

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter and status_filter != "all":
            queryset = queryset.filter(status=status_filter)

        ordering = (request.query_params.get("ordering") or "-created_at").strip()
        if ordering not in VALID_ORDERING:
            ordering = "-created_at"
        queryset = queryset.order_by(ordering)

        page = _parse_int(request.query_params.get("page"), 1, minimum=1)
        page_size = _parse_int(
            request.query_params.get("page_size"), 20, minimum=1, maximum=100
        )

        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        page_items = queryset[start:end]

        serializer = self.get_serializer(page_items, many=True)

        return Response(
            {
                "status": True,
                "message": "Leads retrieved successfully",
                "data": {
                    "results": serializer.data,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "total_pages": (total + page_size - 1) // page_size if total else 0,
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class AdminLeadDetailView(generics.GenericAPIView):
    serializer_class = AdminLeadSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "leads"

    def get_object(self, pk):
        return get_object_or_404(Lead, pk=pk)

    def get(self, request, pk=None):
        lead = self.get_object(pk)
        serializer = self.get_serializer(lead)
        return Response(
            {
                "status": True,
                "message": "Lead retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk=None):
        lead = self.get_object(pk)
        serializer = self.get_serializer(lead, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Lead updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "status": False,
                "message": "Validation error",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Some clients send PUT instead of PATCH; route both to the same handler.
    def put(self, request, pk=None):
        return self.patch(request, pk)

    def delete(self, request, pk=None):
        lead = self.get_object(pk)
        lead.delete()
        return Response(
            {
                "status": True,
                "message": "Lead deleted successfully",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )


class AdminLeadStatsView(APIView):
    """Aggregate counts powering the dashboard stat cards."""

    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "leads"

    def get(self, request):
        total = Lead.objects.count()
        by_status = {
            row["status"]: row["count"]
            for row in Lead.objects.values("status").annotate(count=Count("id"))
        }
        return Response(
            {
                "status": True,
                "message": "Lead stats retrieved successfully",
                "data": {
                    "total": total,
                    "new": by_status.get(Lead.STATUS_NEW, 0),
                    "contacted": by_status.get(Lead.STATUS_CONTACTED, 0),
                    "converted": by_status.get(Lead.STATUS_CONVERTED, 0),
                    "closed": by_status.get(Lead.STATUS_CLOSED, 0),
                },
            },
            status=status.HTTP_200_OK,
        )
