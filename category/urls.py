from django.urls import path
from .views import *

urlpatterns = [
    path("categories/", CategoryViewSet.as_view()),
    path("categories/<int:pk>/", CategoryGetViewSet.as_view()),
    path("category-positions-changes/<int:pk>/",CategoryPositionsChangesViewSet.as_view()),
]