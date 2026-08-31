"""What to poll, and what happened when we did.

The seam is deliberate. `catalog` holds what exists. `status` holds what
we observed. This app holds the machinery between them.

Poller is the tuning and PollRun is the log. Both belong beside the task
that reads them.
"""

import random
import sys
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from catalog.models import Service
from common.models import BaseModel

# A tenth either side of the interval. A hundred services imported at
# once would otherwise all come due on the same second.
JITTER = 0.1


def next_interval_seconds(base, failures, ceiling):
    """Exponential backoff.

    A service in backoff is not checked every five minutes.
    The service screen shows this interval, not the deployment default.
    """
    return min(base * (2**failures), ceiling)


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

    def record(self, ok, at=None):
        """Move the schedule on, from the outcome of one poll.

        Two callers write this. A scheduled poll, and an import, which is
        a poll somebody asked for. They wrote it two ways: the import
        skipped the backoff and the jitter, and set a bare interval.

        Success clears the failure count. A failure backs off, doubling
        to the ceiling. Jitter keeps a hundred services from stampeding
        one provider on the minute.
        """
        at = at or timezone.now()
        if ok:
            self.consecutive_failure_count = 0
            self.last_success_at = at
        else:
            self.consecutive_failure_count += 1
        seconds = next_interval_seconds(
            self.effective_interval_seconds,
            self.consecutive_failure_count,
            self.effective_max_interval_seconds,
        )
        seconds *= 1 + random.uniform(-JITTER, JITTER)
        self.next_at = at + timedelta(seconds=seconds)
        self.save(
            update_fields=["consecutive_failure_count", "last_success_at", "next_at"]
        )

    @property
    def effective_interval_seconds(self):
        return self.interval_seconds or settings.POLL_INTERVAL_SECONDS

    @property
    def effective_cooldown_seconds(self):
        return self.cooldown_seconds or settings.POLL_COOLDOWN_SECONDS

    @property
    def effective_max_interval_seconds(self):
        return self.max_interval_seconds or settings.POLL_MAX_INTERVAL_SECONDS


def exception_name(error):
    """The name that identifies a failure.

    Wrappers stack: `requests.ConnectionError` over urllib3's
    `MaxRetryError` over `NameResolutionError` over `socket.gaierror`.
    The outermost says "the network", the innermost says "errno". The
    deepest one a library defines is the one that names the cause.
    """
    name = type(error).__name__
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        module = type(error).__module__.partition(".")[0]
        if module != "builtins" and module not in sys.stdlib_module_names:
            name = type(error).__name__
        error = error.__cause__ or error.__context__
    return name


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

    @classmethod
    def open(cls, poller, url, provider, at=None):
        """Start the log for one fetch.

        A scheduled poll and an import both make one, and both signed it
        by hand. Nobody types a poll, so the system account does.

        `at` is when the fetch began. An import reads the page before it
        writes anything, so the row is made after the work it times.
        """
        from django.contrib.auth import get_user_model

        author = get_user_model().objects.system()
        return cls.objects.create(
            poller=poller,
            url=url,
            provider=provider,
            started_at=at or timezone.now(),
            created_by=author,
            updated_by=author,
        )

    def finish(self, ok, error=None):
        """Close the log, and move the poller on.

        The schedule follows the outcome of a poll, so the row that
        records the outcome is what moves it. Two callers did this apart,
        and only one of them recorded a failure.
        """
        self.ok = ok
        self.error = str(error) if error is not None else ""
        self.error_type = exception_name(error) if error is not None else ""
        self.finished_at = timezone.now()
        self.save(update_fields=["ok", "error", "error_type", "finished_at"])
        self.poller.record(ok=ok, at=self.finished_at)
        return self

    def __str__(self):
        return f"{self.poller.service} ({self.started_at:%Y-%m-%d %H:%M})"
