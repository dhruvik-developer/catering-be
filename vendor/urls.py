from django.urls import path
from .views import (
    CategoryListCreateAPIView,
    CategoryDetailAPIView,
    VendorListCreateAPIView,
    VendorDetailAPIView,
)


urlpatterns = [
    path("categories/", CategoryListCreateAPIView.as_view()),
    path("categories/<int:pk>/", CategoryDetailAPIView.as_view()),
    path("vendors/", VendorListCreateAPIView.as_view()),
    path("vendors/<int:pk>/", VendorDetailAPIView.as_view()),
]
