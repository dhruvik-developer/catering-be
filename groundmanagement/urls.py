from django.urls import path

from .views import (
    GroundCategoryDetailViewSet,
    GroundCategoryViewSet,
    GroundItemDetailViewSet,
    GroundItemViewSet,
)

urlpatterns = [
    path("ground/categories/", GroundCategoryViewSet.as_view()),
    path("ground/categories/<int:pk>/", GroundCategoryDetailViewSet.as_view()),
    path("ground/items/", GroundItemViewSet.as_view()),
    path("ground/items/<int:pk>/", GroundItemDetailViewSet.as_view()),
]
