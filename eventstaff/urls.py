from django.urls import path
from .views import (
    EventStaffAssignmentViewSet,
    FixedStaffSalaryPaymentViewSet,
    StaffViewSet,
    StaffRoleViewSet,
    WaiterTypeViewSet,
    StaffWithdrawalViewSet,
    StaffRegistrationAPIView,
)

urlpatterns = [
    # Staff Role URLs
    path(
        "roles/",
        StaffRoleViewSet.as_view({"get": "list", "post": "create"}),
        name="staffrole-list",
    ),
    path(
        "roles/<int:pk>/",
        StaffRoleViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="staffrole-detail",
    ),
    # Staff URLs
    path(
        "staff/",
        StaffViewSet.as_view({"get": "list", "post": "create"}),
        name="staff-list",
    ),
    path(
        "staff/<int:pk>/",
        StaffViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="staff-detail",
    ),
    path(
        "staff/waiters/",
        StaffViewSet.as_view({"get": "waiters"}),
        name="staff-waiters",
    ),
    path(
        "staff/<int:pk>/fixed-payment-summary/",
        StaffViewSet.as_view({"get": "fixed_payment_summary"}),
        name="staff-fixed-payment-summary",
    ),
    path(
        "waiter-types/",
        WaiterTypeViewSet.as_view({"get": "list", "post": "create"}),
        name="waiter-type-list",
    ),
    path(
        "waiter-types/<int:pk>/",
        WaiterTypeViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="waiter-type-detail",
    ),
    # Event Staff Assignment Custom Action URLs
    path(
        "event-assignments/event-summary/",
        EventStaffAssignmentViewSet.as_view({"get": "event_summary"}),
        name="eventstaffassignment-event-summary",
    ),
    path(
        "fixed-salary-payments/",
        FixedStaffSalaryPaymentViewSet.as_view({"get": "list", "post": "create"}),
        name="fixed-salary-payment-list",
    ),
    path(
        "fixed-salary-payments/<int:pk>/",
        FixedStaffSalaryPaymentViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="fixed-salary-payment-detail",
    ),
    # Staff Withdrawals URLs
    path(
        "staff-withdrawals/",
        StaffWithdrawalViewSet.as_view({"get": "list", "post": "create"}),
        name="staff-withdrawal-list",
    ),
    path(
        "staff-withdrawals/<int:pk>/",
        StaffWithdrawalViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="staff-withdrawal-detail",
    ),
    # Event Staff Assignment URLs
    path(
        "event-assignments/",
        EventStaffAssignmentViewSet.as_view({"get": "list", "post": "create"}),
        name="eventstaffassignment-list",
    ),
    path(
        "event-assignments/<int:pk>/",
        EventStaffAssignmentViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="eventstaffassignment-detail",
    ),
    path("staff/register/", StaffRegistrationAPIView.as_view(), name="staff-register"),
]
