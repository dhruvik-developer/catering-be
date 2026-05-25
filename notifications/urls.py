from django.urls import path

from . import views

urlpatterns = [
    path(
        "notifications/",
        views.NotificationListView.as_view(),
        name="notification-list",
    ),
    path(
        "notifications/unread-count/",
        views.unread_count,
        name="notification-unread-count",
    ),
    path(
        "notifications/<int:pk>/read/",
        views.mark_read,
        name="notification-mark-read",
    ),
    path(
        "notifications/read-all/",
        views.mark_all_read,
        name="notification-mark-all-read",
    ),
    path(
        "devices/register/",
        views.register_device,
        name="device-register",
    ),
    path(
        "devices/unregister/",
        views.unregister_device,
        name="device-unregister",
    ),
]
