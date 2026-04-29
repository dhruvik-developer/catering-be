from django.contrib import admin

from .models import (
    EventStaffAssignment,
    FixedStaffSalaryPayment,
    Staff,
    StaffRolePermissionAssignment,
)


@admin.register(StaffRolePermissionAssignment)
class StaffRolePermissionAssignmentAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "updated_at")
    list_filter = ("permission__module",)
    search_fields = ("role__name", "permission__code")


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "user_account",
        "role",
        "staff_type",
        "is_active",
        "per_person_rate",
    )
    list_filter = ("role", "staff_type", "is_active")
    search_fields = ("name", "phone", "user_account__username")
    list_editable = ("is_active",)


@admin.register(EventStaffAssignment)
class EventStaffAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "staff",
        "role_at_event",
        "total_days",
        "total_amount",
        "paid_amount",
        "remaining_amount",
        "payment_status",
    )
    list_filter = ("payment_status", "session", "staff__staff_type", "role_at_event")
    search_fields = ("session__booking__name", "staff__name")
    readonly_fields = ("total_amount", "remaining_amount", "payment_status")

    fieldsets = (
        (
            "Assignment Details",
            {
                "fields": (
                    "session",
                    "staff",
                    "role_at_event",
                    "total_days",
                    "per_person_rate",
                )
            },
        ),
        (
            "Payment Tracking (Auto-Calculated)",
            {
                "fields": (
                    "total_amount",
                    "paid_amount",
                    "remaining_amount",
                    "payment_status",
                )
            },
        ),
    )


class EventStaffAssignmentInline(admin.TabularInline):
    model = EventStaffAssignment
    extra = 1
    readonly_fields = ("total_amount", "remaining_amount", "payment_status")
    fields = (
        "staff",
        "role_at_event",
        "total_days",
        "per_person_rate",
        "total_amount",
        "paid_amount",
        "remaining_amount",
        "payment_status",
    )


@admin.register(FixedStaffSalaryPayment)
class FixedStaffSalaryPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "start_date",
        "end_date",
        "months_count",
        "monthly_salary",
        "total_amount",
        "paid_amount",
        "remaining_amount",
        "payment_status",
        "payment_date",
    )
    list_filter = ("payment_status", "start_date")
    search_fields = ("staff__name", "note")
    readonly_fields = (
        "monthly_salary",
        "total_amount",
        "remaining_amount",
        "payment_status",
    )
    fieldsets = (
        (
            "Salary Period",
            {
                "fields": (
                    "staff",
                    "start_date",
                    "end_date",
                    "months_count",
                    "monthly_salary",
                    "total_amount",
                )
            },
        ),
        (
            "Payment Tracking",
            {
                "fields": (
                    "paid_amount",
                    "remaining_amount",
                    "payment_status",
                    "payment_date",
                    "note",
                )
            },
        ),
    )
