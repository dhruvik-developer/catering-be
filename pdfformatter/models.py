from django.conf import settings
from django.db import models
from django.utils.text import slugify


class PdfFormatter(models.Model):
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    html_content = models.TextField(
        help_text="HTML template stored in the database for PDF rendering or preview."
    )
    sample_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional sample/context data for frontend preview or PDF rendering.",
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="pdf_formatters_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pdf_formatter"
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

    def _build_unique_code(self):
        base_code = slugify(self.code or self.name) or "pdf-formatter"
        candidate = base_code[:120]
        suffix = 1

        while type(self).objects.filter(code=candidate).exclude(pk=self.pk).exists():
            suffix_text = f"-{suffix}"
            candidate = f"{base_code[:120 - len(suffix_text)]}{suffix_text}"
            suffix += 1

        return candidate

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        if self.code:
            self.code = slugify(self.code.strip())
        self.code = self._build_unique_code()

        super().save(*args, **kwargs)

        if self.is_default:
            type(self).objects.exclude(pk=self.pk).filter(is_default=True).update(
                is_default=False
            )
