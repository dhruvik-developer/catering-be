from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DeviceToken, Notification
from .serializers import DeviceTokenSerializer, NotificationSerializer


class _Pagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class NotificationListView(ListAPIView):
    """GET /api/notifications/  — paginated history for the current user.

    Pass ?unread=1 to limit to unread only. Pagination follows the same
    shape DRF uses elsewhere in this project ({count, next, previous, results}).
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = _Pagination

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        unread = self.request.query_params.get("unread")
        if str(unread).lower() in {"1", "true", "yes"}:
            qs = qs.filter(is_read=False)
        return qs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_count(request):
    count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return Response(
        {
            "status": True,
            "message": "Unread count fetched.",
            "data": {"unread_count": count},
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read(request, pk):
    updated = Notification.objects.filter(
        pk=pk, recipient=request.user, is_read=False
    ).update(is_read=True)
    return Response(
        {
            "status": True,
            "message": "Marked as read." if updated else "Already read.",
            "data": {"updated": updated},
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    updated = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)
    return Response(
        {
            "status": True,
            "message": "All notifications marked as read.",
            "data": {"updated": updated},
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_device(request):
    """Upsert by `fcm_token`. A token is globally unique — if a different user
    previously held it (shared device, reinstall on the same handset), it is
    reassigned to the current user. That matches what FCM itself does."""
    serializer = DeviceTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token_value = serializer.validated_data["fcm_token"]

    obj, _created = DeviceToken.objects.update_or_create(
        fcm_token=token_value,
        defaults={
            "user": request.user,
            "platform": serializer.validated_data["platform"],
            "device_id": serializer.validated_data.get("device_id", ""),
            "app_version": serializer.validated_data.get("app_version", ""),
            "is_active": True,
        },
    )
    return Response(
        {
            "status": True,
            "message": "Device registered.",
            "data": DeviceTokenSerializer(obj).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unregister_device(request):
    token = request.data.get("fcm_token") or ""
    if not token:
        return Response(
            {
                "status": False,
                "message": "fcm_token is required.",
                "data": {},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    DeviceToken.objects.filter(
        user=request.user, fcm_token=token
    ).update(is_active=False)
    return Response(
        {"status": True, "message": "Device unregistered.", "data": {}}
    )
