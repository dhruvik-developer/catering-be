from django.urls import path
from .views import (
    VendorListCreateAPIView,
    VendorDetailAPIView,
)


urlpatterns = [
    path("vendors/", VendorListCreateAPIView.as_view()),
    path("vendors/<int:pk>/", VendorDetailAPIView.as_view()),
]
