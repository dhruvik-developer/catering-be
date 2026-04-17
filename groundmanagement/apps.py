from django.apps import AppConfig


class GroundmanagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "groundmanagement"

    def ready(self):
        import groundmanagement.signals  # noqa: F401
