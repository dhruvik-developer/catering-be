from django.urls import path
from .views import *

urlpatterns = [
    path("payments/", PaymentViewSet.as_view()),
    path("payments/<int:pk>/", EditPaymentViewSet.as_view()),
    path("all-transaction/", AllTransactionViewSet.as_view()),

]
