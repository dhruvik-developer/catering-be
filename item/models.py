from django.db import models
from ListOfIngridients.models import IngridientsItem
from category.models import Category

class Item(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="items",
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=200)
    base_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    def __str__(self):
        return self.name

class RecipeIngredient(models.Model):
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="recipe_ingredients"
    )

    ingredient = models.ForeignKey(
        IngridientsItem,
        on_delete=models.CASCADE,
        related_name="used_in_recipes"
    )

    quantity = models.FloatField(default=0)
    unit = models.CharField(max_length=50, blank=True, null=True)

    person_count = models.IntegerField(default=100)

    def __str__(self):
        return f"{self.item.name} -> {self.ingredient.name}"
