from django.db import models

class Category(models.Model):
    branch_profile = models.ForeignKey(
        "user.BranchProfile",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="categories",
    )
    name = models.CharField(max_length=100)
    positions = models.IntegerField(default=0)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="subcategories"
    )

    def __str__(self):
        return self.name
