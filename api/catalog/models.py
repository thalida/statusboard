from django.db import models
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from common.models import BaseModel


class Service(BaseModel):
    slug = models.SlugField(
        unique=True,
        blank=True,
        help_text="Derived from the name when left blank.",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    logo = models.URLField(blank=True, default="")
    homepage_url = models.URLField(blank=True, default="")
    is_featured = models.BooleanField(default=False)
    # Derived. Never set by hand: it decides what gets polled.
    watcher_count = models.PositiveIntegerField(default=0, editable=False)

    history = HistoricalRecords()

    def refresh_watcher_count(self):
        """Recount the distinct users tracking any part of this service.

        Distinct users, not items. Someone tracking five Twilio components
        is one watcher, and a counter incremented per item would let one
        person outrank a crowd in the suggestion order.
        """
        from django.contrib.auth import get_user_model

        Service.objects.filter(pk=self.pk).update(
            watcher_count=get_user_model()
            .objects.filter(dashboards__items__component__service=self)
            .distinct()
            .count()
        )

    def save(self, *args, **kwargs):
        # Only on the way in. The slug is the public URL of a service, so
        # a later rename must not move it.
        if not self.slug:
            self.slug = unique_slug(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


def unique_slug(name):
    """A slug from the name, with a counter if it is taken.

    Two providers really can share a name, so this cannot just fail.
    """
    base = slugify(name) or "service"
    slug, suffix = base, 1
    while Service.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


class StatusPage(BaseModel):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="status_page"
    )
    url = models.URLField(unique=True)
    provider = models.CharField(max_length=32, choices=StatusPageProvider.choices)
    # An override, not a derived value. Each adapter works out its own API
    # path from `url` — Statuspage joins "api/v2/summary.json" onto it — so
    # nothing is stored for the normal case. Set this only when that join
    # lands somewhere wrong, such as a page served on one domain whose API
    # lives on another.
    api_url = models.URLField(
        null=True,
        blank=True,
        help_text="Leave blank. Set only when the adapter cannot reach the "
        "API by joining a path onto the page URL.",
    )

    history = HistoricalRecords()


class ServiceComponent(BaseModel):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="components"
    )
    external_id = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    status_page_order = models.IntegerField(default=0)
    is_overall = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["service", "external_id"], name="one_component_per_provider_id"
            ),
            models.UniqueConstraint(
                fields=["service"],
                condition=models.Q(is_overall=True),
                name="one_overall_component_per_service",
            ),
        ]

    def __str__(self):
        return f"{self.service.name} / {self.name}"
