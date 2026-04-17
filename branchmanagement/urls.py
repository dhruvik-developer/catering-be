from django.urls import path

from .views import (
    InvoiceSetupDetailAPIView,
    InvoiceSetupListCreateAPIView,
    PartyInformationDetailAPIView,
    PartyInformationListCreateAPIView,
    GlobalConfigurationListCreateAPIView,
    GlobalConfigurationDetailAPIView,
    BranchItemListCreateAPIView,
    BranchItemDetailAPIView,
    BranchBillListCreateAPIView,
    BranchBillDetailAPIView,
)


urlpatterns = [
    path("invoice-setup/", InvoiceSetupListCreateAPIView.as_view()),
    path("invoice-setup/<int:pk>/", InvoiceSetupDetailAPIView.as_view()),
    path("party-information/", PartyInformationListCreateAPIView.as_view()),
    path("party-information/<int:pk>/", PartyInformationDetailAPIView.as_view()),
    path('global-config/', GlobalConfigurationListCreateAPIView.as_view()),
    path('global-config/<int:pk>/', GlobalConfigurationDetailAPIView.as_view()),
    path('branch-items/', BranchItemListCreateAPIView.as_view()),
    path('branch-items/<int:pk>/', BranchItemDetailAPIView.as_view()),
    path("branch-bills/", BranchBillListCreateAPIView.as_view()),
    path("branch-bills/<int:pk>/", BranchBillDetailAPIView.as_view()),
]
