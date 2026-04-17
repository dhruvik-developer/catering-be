from django.contrib import admin
from .models import EventBooking, EventSession


class EventSessionInline(admin.TabularInline):
    model = EventSession
    extra = 1


@admin.register(EventBooking)
class EventBookingAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "date",
        "status",
    )
    list_filter = ("status", "date")
    search_fields = ("name", "mobile_no")
    inlines = [EventSessionInline]
