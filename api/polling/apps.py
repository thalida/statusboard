from django.apps import AppConfig


class PollingConfig(AppConfig):
    name = "polling"

    def ready(self):
        from polling import signals  # noqa: F401
