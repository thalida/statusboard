from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from catalog.models import Service, ServiceComponent
from common.models import BaseModel
from status.choices import (
    CLOSED_PHASES,
    EVENT_PHASES_BY_KIND,
    EventKind,
    EventSource,
    Severity,
    StatusSource,
)


class ComponentStatus(BaseModel):
    """One row per severity span. The open row is the current one.

    A poll appends. It never overwrites. The table is the history.
    """

    component = models.ForeignKey(
        ServiceComponent, on_delete=models.CASCADE, related_name="statuses"
    )
    severity = models.IntegerField(choices=Severity.choices)
    source = models.CharField(
        max_length=32,
        choices=StatusSource.choices,
        help_text=(
            "How the severity was arrived at: published by the provider, "
            "taken as the worst of the components, or derived from the "
            "open incidents."
        ),
    )
    started_at = models.DateTimeField(verbose_name="Started")
    ended_at = models.DateTimeField(verbose_name="Ended", null=True, blank=True)
    # Which poll wrote this. A wrong or stale reading is otherwise
    # untraceable: you can see what it says and not where it came from.
    # SET_NULL because runs are a log and may be pruned.
    poll_run = models.ForeignKey(
        "polling.PollRun",
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )

    def clean(self):
        """A reading ends after it starts, and cites its own service.

        A run names a poller and a poller names one service. Citing
        another service's run says a page was read that never mentions
        this component.
        """
        super().clean()
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValidationError(
                {"ended_at": "A reading cannot end before it starts."}
            )
        if self.poll_run_id is None or self.component_id is None:
            return
        if self.poll_run.poller.service_id != self.component.service_id:
            raise ValidationError({"poll_run": "That poll read another service."})

    def __str__(self):
        return f"{self.component} ({self.get_severity_display()})"

    class Meta(BaseModel.Meta):
        verbose_name = "component status"
        verbose_name_plural = "component statuses"
        constraints = [
            models.UniqueConstraint(
                fields=["component"],
                condition=models.Q(ended_at__isnull=True),
                name="one_open_status_per_component",
            ),
            # Both ends are written here, unlike an event's, so the
            # database can hold this one.
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | models.Q(ended_at__gte=models.F("started_at")),
                name="status_ends_after_it_starts",
            ),
        ]
        indexes = [
            models.Index(
                fields=["severity"],
                condition=models.Q(ended_at__isnull=True),
                name="open_by_severity",
            )
        ]


class ServiceEventQuerySet(models.QuerySet):
    def live(self, kind=None):
        """Still worth showing.

        An open phase for either kind. A maintenance window is also over
        once it ends, and a provider often leaves the phase behind.

        Counts and the item beside them read this. A wider count shows
        "+3 more" for nothing.
        """
        events = self.exclude(phase__in=CLOSED_PHASES)
        if kind is not None:
            events = events.filter(kind=kind)
        if kind == EventKind.MAINTENANCE:
            events = events.filter(
                Q(ends_at__isnull=True) | Q(ends_at__gte=timezone.now())
            )
        return events


class ServiceEvent(BaseModel):
    """A provider's record of an incident or a maintenance window.

    Providers publish both as one object. This is one model with a `kind`.
    """

    objects = ServiceEventQuerySet.as_manager()

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="events"
    )
    # Null until a provider claims this event. We open events a
    # provider never published, and they have no id of theirs.
    external_id = models.CharField(
        verbose_name="Provider ID", max_length=200, null=True, blank=True
    )
    # Who opened it, never rewritten by a claim. `external_id IS NULL`
    # cannot answer this: claiming fills the column in, which destroys
    # the fact that we found the outage first.
    detected_by = models.CharField(
        max_length=32,
        choices=EventSource.choices,
        default=EventSource.PROVIDER,
        db_default=EventSource.PROVIDER,
    )
    kind = models.CharField(max_length=32, choices=EventKind.choices)
    title = models.CharField(max_length=500)
    phase = models.CharField(max_length=32)
    # No rule that the end follows the start. Providers back-date a
    # resolution below the recorded start. GitHub and OpenAI both
    # publish incidents that end before they began.
    #
    # This mirrors the page. A rule here would fail the poll.
    starts_at = models.DateTimeField(verbose_name="Starts")
    ends_at = models.DateTimeField(verbose_name="Ends", null=True, blank=True)
    # No component is a valid case. A provider can publish an event
    # against the whole service. An FK cannot hold that case.
    affected_components = models.ManyToManyField(
        ServiceComponent, blank=True, related_name="events"
    )
    # Which poll wrote this. A wrong or stale reading is otherwise
    # untraceable: you can see what it says and not where it came from.
    # SET_NULL because runs are a log and may be pruned.
    poll_run = models.ForeignKey(
        "polling.PollRun",
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )

    class Meta(BaseModel.Meta):
        constraints = [
            # Partial. Two events we opened both hold null, and null
            # does not collide with null in Postgres anyway. Stating
            # the condition says the exemption is deliberate.
            models.UniqueConstraint(
                fields=["service", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="one_event_per_provider_id",
            )
        ]
        indexes = [
            # `live` reads this for every component on a page. The
            # only index was the unique key, which serves neither
            # column. Ordered as the filter narrows: the service first,
            # then the kind, then the phase it excludes.
            models.Index(
                fields=["service", "kind", "phase"], name="events_by_service_and_kind"
            )
        ]

    def __str__(self):
        return self.title

    def clean(self):
        # A phase belongs to one kind. Block a combination no provider
        # would publish, such as a maintenance phase on an incident.
        valid = EVENT_PHASES_BY_KIND.get(self.kind)
        if valid is not None and self.phase not in valid.values:
            raise ValidationError(
                {"phase": f"{self.phase!r} is not a phase of a {self.kind}."}
            )
        # The poll that wrote it read this event's own service.
        if self.poll_run_id and self.poll_run.poller.service_id != self.service_id:
            raise ValidationError({"poll_run": "That poll read another service."})

    def components_of_another_service(self):
        """Any affected component that is not this event's own.

        The relation is many to many. It is not set until the row is
        saved, and `clean` cannot see it. The callers that can check it
        use this.
        """
        return self.affected_components.exclude(service_id=self.service_id)


class EventUpdate(BaseModel):
    """One posted update within an event's timeline."""

    event = models.ForeignKey(
        ServiceEvent, on_delete=models.CASCADE, related_name="updates"
    )
    phase = models.CharField(max_length=32)
    body = models.TextField()
    posted_at = models.DateTimeField(verbose_name="Posted")
    # Who wrote this post. A claimed event holds both: our detection
    # first, then the provider's log.
    source = models.CharField(
        max_length=32,
        choices=EventSource.choices,
        default=EventSource.PROVIDER,
        db_default=EventSource.PROVIDER,
    )

    def clean(self):
        """A phase belongs to one kind, the same rule the event follows.

        An update saying `scheduled` on an incident describes something
        no provider publishes.
        """
        super().clean()
        if self.event_id is None:
            return
        valid = EVENT_PHASES_BY_KIND.get(self.event.kind)
        if valid is not None and self.phase not in valid.values:
            raise ValidationError(
                {"phase": f"{self.phase!r} is not a phase of a {self.event.kind}."}
            )

    def __str__(self):
        return f"{self.event} ({self.phase})"

    class Meta(BaseModel.Meta):
        ordering = ["-posted_at"]
