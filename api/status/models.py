from django.core.exceptions import ValidationError
from django.db import models

from catalog.choices import StatusPageProvider
from catalog.models import Poller, Service, ServiceComponent
from common.models import BaseModel
from status.choices import EVENT_PHASES_BY_KIND, EventKind, Severity, StatusSource


class ComponentStatus(BaseModel):
    """One row per severity span. The open row is the current one.

    A poll appends. It never overwrites. The table is the history.
    """

    component = models.ForeignKey(
        ServiceComponent, on_delete=models.CASCADE, related_name="statuses"
    )
    severity = models.IntegerField(choices=Severity.choices)
    source = models.CharField(max_length=32, choices=StatusSource.choices)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["component"],
                condition=models.Q(ended_at__isnull=True),
                name="one_open_status_per_component",
            )
        ]
        indexes = [
            models.Index(
                fields=["severity"],
                condition=models.Q(ended_at__isnull=True),
                name="open_by_severity",
            )
        ]


class ServiceEvent(BaseModel):
    """A provider's record of an incident or a maintenance window.

    Providers publish both as one object. This is one model with a `kind`.
    """

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="events"
    )
    external_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=32, choices=EventKind.choices)
    title = models.CharField(max_length=500)
    phase = models.CharField(max_length=32)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    # No component is a valid case. A provider can publish an event
    # against the whole service. An FK cannot hold that case.
    affected_components = models.ManyToManyField(
        ServiceComponent, blank=True, related_name="events"
    )

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["service", "external_id"], name="one_event_per_provider_id"
            )
        ]

    def clean(self):
        # A phase belongs to one kind. Block a combination no provider
        # would publish, such as a maintenance phase on an incident.
        valid = EVENT_PHASES_BY_KIND.get(self.kind)
        if valid is not None and self.phase not in valid.values:
            raise ValidationError(
                {"phase": f"{self.phase!r} is not a phase of a {self.kind}."}
            )


class EventUpdate(BaseModel):
    """One posted update within an event's timeline."""

    event = models.ForeignKey(
        ServiceEvent, on_delete=models.CASCADE, related_name="updates"
    )
    phase = models.CharField(max_length=32)
    body = models.TextField()
    posted_at = models.DateTimeField()

    class Meta(BaseModel.Meta):
        ordering = ["-posted_at"]


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
