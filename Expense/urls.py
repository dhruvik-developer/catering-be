from django.urls import path
from .views import *

urlpatterns = [
    path("expenses/", ExpenseView.as_view()),
    path("expenses/<int:pk>/", ExpenseDetailView.as_view()),
    path("expenses-categories/", CategoryView.as_view()),
    path("expenses-categories/<int:pk>/", CategoryDetailView.as_view()),
    path("entities/", ExpenseEntityView.as_view()),
    path("entities/<int:pk>/", ExpenseEntityDetailView.as_view()),
    path("entities/<int:pk>/summary/", ExpenseEntitySummaryView.as_view()),
]