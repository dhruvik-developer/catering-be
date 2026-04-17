from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class ExpenseEntity(models.Model):
    ENTITY_TYPE_CHOICES = [
        ('EMPLOYEE', 'Employee'),
        ('VENDOR', 'Vendor'),
        ('OTHER', 'Other'),
    ]
    name = models.CharField(max_length=200)
    entity_type = models.CharField(
        max_length=50,
        choices=ENTITY_TYPE_CHOICES,
        default='OTHER'
    )
    contact_info = models.CharField(max_length=250, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_entity_type_display()})"


class Expense(models.Model):

    PAYMENT_MODE_CHOICES = [
        ('CASH', 'Cash'),
        ('ONLINE', 'Online'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)  # Optional field
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='expenses'
    )
    entity = models.ForeignKey(
        ExpenseEntity,
        on_delete=models.SET_NULL,
        related_name='expenses',
        null=True, 
        blank=True
    )
    payment_mode = models.CharField(
        max_length=10,
        choices=PAYMENT_MODE_CHOICES,
        default='CASH'
    )
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.title