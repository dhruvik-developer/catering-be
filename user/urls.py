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
    path("users/<uuid:id>/branch/", UserBranchAssignmentAPIView.as_view()),
    path("change-password/", TenantChangePasswordAPIView.as_view()),
    path("change-password/<uuid:id>/", ChangePasswordAPIView.as_view()),
    path("forgot-password/", PasswordResetRequestAPIView.as_view()),
    path("reset-password/", PasswordResetConfirmAPIView.as_view()),
    path("update-note/<int:pk>/", NoteViewSet.as_view()),
    path(
        "branch-profiles/",
        BranchProfileListCreateAPIView.as_view(),
        name="branch-profile-list",
    ),
    path(
        "branch-profiles/<int:id>/",
        BranchProfileDetailAPIView.as_view(),
        name="branch-profile-detail",
    ),
    path(
        "branch-profiles/<int:id>/users/",
        BranchProfileUsersAPIView.as_view(),
        name="branch-profile-users",
    ),
    path(
        "business-profiles/",
        BusinessProfileAPIView.as_view(),
        name="business-profile-list",
    ),
    path(
        "business-profiles/language/",
        BusinessProfileLanguageAPIView.as_view(),
        name="business-profile-language",
    ),
    path(
        "business-profiles/<int:id>/",
        BusinessProfileDetailAPIView.as_view(),
        name="business-profile-detail",
    ),
]
