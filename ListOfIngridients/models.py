from django.db import models


# Create your models here.
class IngridientsCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    positions = models.IntegerField(default=0)
    is_common = models.BooleanField(
        default=False,
        help_text="Always include items from this category in all event orders",
    )

    def __str__(self):
        return self.name


class IngridientsItem(models.Model):
    category = models.ForeignKey(
        IngridientsCategory, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name