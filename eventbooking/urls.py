from django.urls import path
from .views import *

urlpatterns = [
    path("event-bookings/", EventBookingViewSet.as_view()),
    path("event-bookings/<int:pk>/", EventBookingGetViewSet.as_view()),
    path("pending-event-bookings/", PendingEventBookingViewSet.as_view()),
    path("event-item-configs/", EventItemConfigViewSet.as_view()),
    path("event-item-configs/<int:pk>/", EventItemConfigDetailViewSet.as_view()),
    path("ingredient-vendor-assignments/", IngredientVendorAssignmentViewSet.as_view()),
    path("ingredient-vendor-assignments/<int:pk>/", IngredientVendorAssignmentDetailViewSet.as_view()),
    path(
        "event-sessions/<int:session_id>/checklist/",
        SessionChecklistView.as_view(),
        name="session-checklist",
    ),
    # Vendor portal — accept/decline (session OR per-item) and dispatch
    # details. See views.VendorAssignmentRespondView for request shapes.
    path(
        "event-vendor-assignments/mine/",
        MyVendorAssignmentsView.as_view(),
        name="vendor-assignment-mine",
    ),
    path(
        "event-vendor-assignments/<int:pk>/respond/",
        VendorAssignmentRespondView.as_view(),
        name="vendor-assignment-respond",
    ),
    path(
        "event-vendor-assignments/<int:pk>/dispatch/",
        VendorAssignmentDispatchView.as_view(),
        name="vendor-assignment-dispatch",
    ),
]
