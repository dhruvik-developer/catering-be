from django.urls import path

from tenancy.views import (
    ClientDetailAPIView,
    ClientListCreateAPIView,
    MyTenantAPIView,
    SubscriptionPlanDetailAPIView,
    SubscriptionPlanListCreateAPIView,
    TenantProvisionAPIView,
)


urlpatterns = [
    path("subscription-plans/", SubscriptionPlanListCreateAPIView.as_view()),
    path("subscription-plans/<uuid:id>/", SubscriptionPlanDetailAPIView.as_view()),
    path("tenants/", ClientListCreateAPIView.as_view()),
    path("tenants/<uuid:id>/", ClientDetailAPIView.as_view()),
    path("tenants/<uuid:id>/provision/", TenantProvisionAPIView.as_view()),
    path("me/tenant/", MyTenantAPIView.as_view()),
]
