from django.conf import settings
from django.db import models

from catalog.models import ServiceComponent
from common.models import BaseModel


class Dashboard(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboards"
    )
    name = models.CharField(max_length=200, default="My board")
    is_default = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="one_default_dashboard_per_owner",
            )
        ]

    def __str__(self):
        return self.name


class DashboardItem(BaseModel):
    """A tracked component. There is no position column. Order is a query."""

    dashboard = models.ForeignKey(
        Dashboard, on_delete=models.CASCADE, related_name="items"
    )
    component = models.ForeignKey(
        ServiceComponent, on_delete=models.CASCADE, related_name="tracked_by"
    )

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["dashboard", "component"],
                name="one_item_per_component_per_dashboard",
            )
        ]
