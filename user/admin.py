from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import UserModel

class CustomUserAdmin(UserAdmin):
    model = UserModel
    list_display = ("username", "email", "is_staff", "is_active")
    search_fields = ("username", "email")
    ordering = ("username",)

# Register the custom user model
admin.site.register(UserModel, CustomUserAdmin)
