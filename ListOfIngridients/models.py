from django.db import models


# Create your models here.
class IngridientsCategory(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="ingredient_categories",
    )
    name = models.CharField(max_length=100)
    positions = models.IntegerField(default=0)
    is_common = models.BooleanField(
        default=False,
        help_text="Always include items from this category in all event orders",
    )

    def __str__(self):
        return self.name


class IngridientsItem(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="ingredient_items",
    )
    category = models.ForeignKey(
        IngridientsCategory, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name
