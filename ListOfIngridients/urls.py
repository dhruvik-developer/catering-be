from django.urls import path
from .views import *

urlpatterns = [
    path("ingredients-categories/", IngridientsCategoryViewset.as_view()),
    path("ingredients-categories/<int:pk>/", IngridientsCategoryViewset.as_view()),
    path("ingredients-items/", IngridientsItemViewset.as_view()),
    path("ingredients-items/<int:pk>/", IngridientsItemViewset.as_view()),
]
