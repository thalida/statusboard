"""What to poll, and what happened when we did.

The seam is deliberate. `catalog` holds what exists. `status` holds what
we observed. This app holds the machinery between them.

Poller is the tuning and PollRun is the log. Both belong beside the task
that reads them.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from catalog.models import Service
from common.models import BaseModel


class Poller(BaseModel):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="poller"
    )

    # Admin-tunable. Null inherits the deployment default.
    # At least a second. Zero is not an interval. It would ask the
    # provider again the moment the last answer arrived.
    interval_seconds = models.PositiveIntegerField(
        verbose_name="Interval",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    cooldown_seconds = models.PositiveIntegerField(
        verbose_name="Cooldown",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    max_interval_seconds = models.PositiveIntegerField(
        verbose_name="Longest interval",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    is_paused = models.BooleanField(verbose_name="Paused", default=False)
    note = models.TextField(blank=True, default="", help_text="Why this was tuned.")

    # Written by the poller.
    next_at = models.DateTimeField(
        verbose_name="Next poll", null=True, blank=True, db_index=True
    )
    last_success_at = models.DateTimeField(
        verbose_name="Last success", null=True, blank=True
    )
    consecutive_failure_count = models.PositiveIntegerField(
        verbose_name="Failures", default=0
    )

    history = HistoricalRecords()

    def clean(self):
        """The ceiling is a ceiling, so it cannot sit below the interval.

        Backoff is `min(interval * 2 ** failures, ceiling)`. A ceiling
        under the interval takes effect with no failures at all. The
        longest interval would then make the poller faster than the one
        it was given.
        """
        super().clean()
        interval = self.interval_seconds
        ceiling = self.max_interval_seconds
        if interval and ceiling and ceiling < interval:
            raise ValidationError(
                {"max_interval_seconds": "This cannot be shorter than the interval."}
            )

    def __str__(self):
        return str(self.service)

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
    started_at = models.DateTimeField(verbose_name="Started")
    finished_at = models.DateTimeField(verbose_name="Finished", null=True, blank=True)

    def clean(self):
        """A poll finishes after it starts. Both ends are written here."""
        super().clean()
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValidationError(
                {"finished_at": "A poll cannot finish before it starts."}
            )

    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    error_type = models.CharField(
        verbose_name="Error type",
        max_length=100,
        blank=True,
        default="",
    )

    class Meta(BaseModel.Meta):
        constraints = [
            # A run is created before it is attempted, so an unfinished
            # row has nothing to say yet. Once it has finished, a failure
            # that cannot name its cause is a failure nobody can group,
            # filter or count.
            models.CheckConstraint(
                condition=Q(finished_at__isnull=True) | Q(ok=True) | ~Q(error_type=""),
                name="a_failed_run_names_its_error",
            )
        ]

    def __str__(self):
        return f"{self.poller.service} ({self.started_at:%Y-%m-%d %H:%M})"
