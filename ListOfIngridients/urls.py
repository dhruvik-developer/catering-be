from django.urls import path
from .views import *

urlpatterns = [
    # legacy spelling
    path("ingridients-categories/", IngridientsCategoryViewset.as_view()),
    path("ingridients-categories/<int:pk>/", IngridientsCategoryViewset.as_view()),
    path("ingridients-item/", IngridientsItemViewset.as_view()),
    path("ingridients-item/<int:pk>/", IngridientsItemViewset.as_view()),
    # canonical endpoints requested by API spec
    path("ingredients-categories/", IngridientsCategoryViewset.as_view()),
    path("ingredients-categories/<int:pk>/", IngridientsCategoryViewset.as_view()),
    path("ingredients-items/", IngridientsItemViewset.as_view()),
    path("ingredients-items/<int:pk>/", IngridientsItemViewset.as_view()),
]