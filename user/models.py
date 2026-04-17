from django.db import models
from django.contrib.auth.models import AbstractUser
from rest_framework_simplejwt.tokens import RefreshToken
import uuid


class UserModel(AbstractUser):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True
    )

    @property
    def tokens(self):
        refresh = RefreshToken.for_user(self)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}

    class Meta:
        db_table = "user"


class Note(models.Model):
    title = models.CharField(max_length=255)
    content = models.JSONField(default=list)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "Note"


class BusinessProfile(models.Model):
    caters_name = models.CharField("Caters Name", max_length=255)
    phone_number = models.CharField("Phone Number", max_length=20)
    whatsapp_number = models.CharField(
        "WhatsApp Number", max_length=20, blank=True, null=True
    )
    fssai_number = models.CharField(
        "FSSAI Number", max_length=50, blank=True, null=True
    )
    godown_address = models.TextField("Godown Address", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.caters_name

    class Meta:
        db_table = "BusinessProfile"
        verbose_name = "Business Profile"
        verbose_name_plural = "Business Profiles"
