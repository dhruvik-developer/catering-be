from django.db import models

class StokeCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class StokeItem(models.Model):

    TYPE_CHOICES = [
        ("KG", "કિલોગ્રામ"),  # Kilograms
        ("G", "ગ્રામ"),  # Grams
        ("L", "લીટર"),  # Liters
        ("ML", "મિલીલીટર"),  # Milliliters
        ("QTY", "જથ્થો"),  # Quantity
    ]

    name = models.CharField(max_length=200, unique=True)
    category = models.ForeignKey(
        StokeCategory, on_delete=models.CASCADE, related_name="stokeitem"
    )
    nte_price = models.CharField(max_length=250)
    total_price = models.CharField(max_length=250)
    quantity = models.DecimalField(max_digits=100, decimal_places=0)
    alert = models.CharField(max_length=500)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    def __str__(self):
        return f"{self.name} - {self.quantity} {self.alert}"
