from django.urls import path
from .views import *

urlpatterns = [
    path("login/", LoginViewSet.as_view()),
    path("refresh-token/", TenantTokenRefreshView.as_view()),
    path("subscription-plans/", SubscriptionPlanListCreateAPIView.as_view()),
    path("subscription-plans/<uuid:id>/", SubscriptionPlanDetailAPIView.as_view()),
    path("tenants/", TenantListCreateAPIView.as_view()),
    path("tenants/<uuid:id>/", TenantDetailAPIView.as_view()),
    path("tenants/<uuid:id>/provision/", TenantProvisionAPIView.as_view()),
    path("me/tenant/", MyTenantAPIView.as_view()),
    path("get-note/", NoteViewSet.as_view()),
    path("users/", UserCreateAPIView.as_view()),
    path("users/<uuid:id>/", UserCreateAPIView.as_view()),
    path("change-password/<uuid:id>/", ChangePasswordAPIView.as_view()),
    path("update-note/<int:pk>/", NoteViewSet.as_view()),
    path(
        "business-profiles/",
        BusinessProfileAPIView.as_view(),
        name="business-profile-list",
    ),
    path(
        "business-profiles/<int:id>/",
        BusinessProfileDetailAPIView.as_view(),
        name="business-profile-detail",
    ),
]
