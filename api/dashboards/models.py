from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from catalog.models import ServiceComponent
from common.models import BaseModel


class Dashboard(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboards"
    )
    name = models.CharField(max_length=200, default="My board")

    # Which board is the default is on the user, as `default_dashboard`.
    # A column here would be one flag per board with a rule saying only
    # one may be set, and a rule can be broken. One pointer cannot.

    @property
    def is_default(self):
        return self.owner.default_dashboard_id == self.pk

    def delete(self, *args, **kwargs):
        """The default moves on. The last board does not go at all.

        Deleting a user takes their boards with it, and that path is a
        bulk one that never reaches this method, so an account can still
        be closed.
        """
        owner = self.owner
        heir = (
            Dashboard.objects.filter(owner=owner)
            .exclude(pk=self.pk)
            .order_by("created_at")
            .first()
        )
        if heir is None:
            raise ValidationError("An owner keeps their last board.")
        with transaction.atomic():
            was_default = self.is_default
            result = super().delete(*args, **kwargs)
            if was_default:
                owner.default_dashboard = heir
                owner.save(update_fields=["default_dashboard"])
        return result

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
