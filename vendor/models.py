from django.db import models
from ListOfIngridients.models import IngridientsCategory


# Create your models here.
class Vendor(models.Model):
    name = models.CharField(max_length=200)
    mobile_no = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class VendorCategory(models.Model):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="vendor_categories"
    )
    category = models.ForeignKey(IngridientsCategory, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.vendor.name} - {self.category.name}"
