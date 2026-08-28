from django.conf import settings
from django.db import models, transaction

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

    def save(self, *args, **kwargs):
        """A new default stands down the old one.

        An owner has one default, and the column holds that. Without this
        the second one is an integrity error, which the person who ticked
        the box can do nothing about. Moving the flag is what they meant.
        """
        with transaction.atomic():
            if self.is_default:
                Dashboard.objects.filter(owner=self.owner, is_default=True).exclude(
                    pk=self.pk
                ).update(is_default=False)
            super().save(*args, **kwargs)

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

    def save(self, *args, **kwargs):
        """Keep the service's watcher count true.

        It is derived from these rows and it decides what gets polled, so
        it cannot depend on which door the row came through. Doing this
        in the board endpoints alone left anything added in the admin
        uncounted, and therefore unpolled.
        """
        super().save(*args, **kwargs)
        self.component.service.refresh_watcher_count()

    def delete(self, *args, **kwargs):
        service = self.component.service
        super().delete(*args, **kwargs)
        service.refresh_watcher_count()

    def __str__(self):
        return f"{self.dashboard} / {self.component}"
