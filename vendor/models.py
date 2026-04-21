from django.conf import settings
from django.db import models
from ListOfIngridients.models import IngridientsCategory


# Create your models here.
class Vendor(models.Model):
    user_account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="vendor_profile",
        verbose_name="Login User",
        help_text="Optional login account for this vendor.",
    )
    name = models.CharField(max_length=200)
    mobile_no = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="vendors_created",
        verbose_name="Created By",
    )

    def __str__(self):
        login_label = self.user_account.username if self.user_account else "No Login"
        return f"{self.name} ({login_label})"

    def save(self, *args, **kwargs):
        if self.user_account:
            if not self.user_account.first_name:
                self.user_account.first_name = self.name
            self.user_account.is_active = self.is_active
            self.user_account.save(update_fields=["first_name", "is_active"])
        super().save(*args, **kwargs)


class VendorCategory(models.Model):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="vendor_categories"
    )
    category = models.ForeignKey(IngridientsCategory, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.vendor.name} - {self.category.name}"
