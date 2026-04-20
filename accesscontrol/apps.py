from django.apps import AppConfig


class AccesscontrolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accesscontrol"
    verbose_name = "Access Control"

    def ready(self):
        from . import signals  # noqa: F401
