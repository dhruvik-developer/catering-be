from django.urls import path
from .views import *

urlpatterns = [
    path("items/", ItemViewSet.as_view()),
    path("items/<int:pk>/", ItemGetViewSet.as_view()),
    path("recipes/", RecipeIngredientViewSet.as_view()),
    path("recipes/<int:pk>/", RecipeIngredientDetailViewSet.as_view()),
]
