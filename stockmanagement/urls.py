from django.urls import path
from .views import *

urlpatterns = [
    path("stoke-categories/", StokeCategoryViewSet.as_view()),
    path("stoke-categories/<int:pk>/", EditeStokeCategoryViewSet.as_view()),
    path("stoke-items/", StokeItemViewSet.as_view()),
    path("stoke-items/<int:pk>/", EditStokeItemViewSet.as_view()),
    path("add-stoke-item/", AddRemoveStokeItemViewSet.as_view()),
    path("alert-stoke-item/", AlertstokeItemViewSet.as_view()),

]
