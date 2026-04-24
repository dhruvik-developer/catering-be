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
]
