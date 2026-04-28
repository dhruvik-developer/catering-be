from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    positions = models.IntegerField(default=0)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="subcategories"
    )

    def __str__(self):
        return self.name