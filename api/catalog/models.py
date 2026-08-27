from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from common.models import BaseModel


class Service(BaseModel):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    logo = models.URLField(blank=True, default="")
    homepage_url = models.URLField(blank=True, default="")
    is_featured = models.BooleanField(default=False)
    watcher_count = models.PositiveIntegerField(default=0)

    history = HistoricalRecords()

    def __str__(self):
        return self.name


class StatusPage(BaseModel):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="status_page"
    )
    url = models.URLField(unique=True)
    provider = models.CharField(max_length=32, choices=StatusPageProvider.choices)
    api_url = models.URLField(
        null=True, blank=True, help_text="Null unless the derivation from url fails."
    )

    history = HistoricalRecords()


class Poller(BaseModel):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="poller"
    )

    # Admin-tunable. Null inherits the deployment default.
    interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    cooldown_seconds = models.PositiveIntegerField(null=True, blank=True)
    max_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_paused = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="", help_text="Why this was tuned.")

    # Written by the poller.
    next_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    consecutive_failure_count = models.PositiveIntegerField(default=0)

    history = HistoricalRecords()

    @property
    def effective_interval_seconds(self):
        return self.interval_seconds or settings.POLL_INTERVAL_SECONDS

    @property
    def effective_cooldown_seconds(self):
        return self.cooldown_seconds or settings.POLL_COOLDOWN_SECONDS

    @property
    def effective_max_interval_seconds(self):
        return self.max_interval_seconds or settings.POLL_MAX_INTERVAL_SECONDS


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
