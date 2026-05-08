from django.db import models


class Lead(models.Model):
    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_CONVERTED = "converted"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_CONVERTED, "Converted"),
        (STATUS_CLOSED, "Closed"),
    ]

    full_name = models.CharField(max_length=120)
    email = models.EmailField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, default="")
    company = models.CharField(max_length=120, blank=True, default="")
    message = models.TextField(max_length=2000)
    source = models.CharField(max_length=60, blank=True, default="website")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"
