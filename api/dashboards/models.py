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
    is_default = models.BooleanField(
        verbose_name="Default",
        default=False,
        help_text=(
            "An owner always reads a board, so this cannot be cleared. "
            "Marking another board default is what moves it."
        ),
    )

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="one_default_dashboard_per_owner",
            )
        ]

    def save(self, *args, **kwargs):
        """A new default stands down the old one, and one always stands.

        An owner reads a board when they sign in, so the flag has to be
        somewhere. Marking a second board moves it, which is what the
        person ticking the box meant; without this it was an integrity
        error they could do nothing about. Clearing the last one would
        leave nothing to open, so it does not clear.
        """
        with transaction.atomic():
            siblings = Dashboard.objects.filter(owner=self.owner).exclude(pk=self.pk)
            if self.is_default:
                siblings.filter(is_default=True).update(is_default=False)
            elif not siblings.filter(is_default=True).exists():
                self.is_default = True
                fields = kwargs.get("update_fields")
                if fields is not None:
                    kwargs["update_fields"] = [*fields, "is_default"]
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """The flag moves on. The last board does not go at all.

        Deleting a user takes their boards with it, and that path is a
        bulk one that never reaches this method, so an account can still
        be closed.
        """
        siblings = Dashboard.objects.filter(owner=self.owner).exclude(pk=self.pk)
        heir = siblings.order_by("created_at").first()
        if heir is None:
            raise ValidationError("An owner keeps their last board.")
        with transaction.atomic():
            was_default = self.is_default
            result = super().delete(*args, **kwargs)
            if was_default:
                heir.is_default = True
                heir.save(update_fields=["is_default"])
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
