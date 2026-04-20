from django.urls import path

from accesscontrol.views import (
    MyPermissionAPIView,
    PermissionModuleListAPIView,
    PermissionSubjectListAPIView,
    StaffRolePermissionAssignmentAPIView,
    UserPermissionAssignmentAPIView,
)


urlpatterns = [
    path("access-control/modules/", PermissionModuleListAPIView.as_view()),
    path("access-control/users/", PermissionSubjectListAPIView.as_view()),
    path(
        "access-control/users/<uuid:user_id>/permissions/",
        UserPermissionAssignmentAPIView.as_view(),
    ),
    path(
        "access-control/staff-roles/<int:role_id>/permissions/",
        StaffRolePermissionAssignmentAPIView.as_view(),
    ),
    path("me/permissions/", MyPermissionAPIView.as_view()),
]
