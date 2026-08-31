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

    # Which board is the default sits on the user, as
    # `default_dashboard`. A column here would be a flag per board with
    # a rule saying only one may be set. A rule breaks. A pointer does
    # not.

    @property
    def is_default(self):
        return self.owner.default_dashboard_id == self.pk

    def delete(self, *args, **kwargs):
        """The default moves on. The last board does not go at all.

        Deleting a user takes their boards with it. That path is a bulk
        one and never reaches this method, so an account still closes.
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

    def __str__(self):
        return f"{self.dashboard} / {self.component}"
