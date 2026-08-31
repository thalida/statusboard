from django.apps import AppConfig


class DashboardsConfig(AppConfig):
    name = "dashboards"

    def ready(self):
        from dashboards import signals  # noqa: F401
