"""What to poll, and what happened when we did.

The seam is deliberate. `catalog` holds what exists, `status` holds what we
observed, and this app holds the machinery between them. Poller is the
tuning and PollRun is the log, so both belong beside the task that reads
them rather than split across two other apps.
"""

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from catalog.models import Service
from common.models import BaseModel


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


class PollRun(BaseModel):
    """One poll attempt against a service's status page.

    `url` and `provider` are snapshots. A service can change its status
    page later. This row stays readable as it was polled.
    """

    poller = models.ForeignKey(Poller, on_delete=models.CASCADE, related_name="runs")
    url = models.URLField()
    provider = models.CharField(max_length=32, choices=StatusPageProvider.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
