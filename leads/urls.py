from django.urls import path

from .views import (
    AdminLeadDetailView,
    AdminLeadListView,
    AdminLeadStatsView,
    PublicContactView,
)

urlpatterns = [
    # Public website lead submission (unauthenticated)
    path("public/contact/", PublicContactView.as_view()),
    # Admin lead management (authenticated)
    path("leads/", AdminLeadListView.as_view()),
    path("leads/stats/", AdminLeadStatsView.as_view()),
    path("leads/<int:pk>/", AdminLeadDetailView.as_view()),
]
