from django.urls import path
from .views import *

urlpatterns = [
    path("login/", LoginViewSet.as_view()),
    path("add-note/", NoteViewSet.as_view()),
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
