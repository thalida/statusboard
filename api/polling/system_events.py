"""Events we open when a provider explains nothing.

A provider can move a component to Degraded and never write an
incident. An event-only feed would hide that outage, and the closed
`ComponentStatus` span is exposed nowhere else.

`ComponentStatus` stays the truth. An event here is a projection of it,
written by this module alone and rebuildable from nothing. That is what
keeps it from being a second answer to the same question.
"""

from django.utils import timezone

from status.choices import EventKind, EventSource, IncidentPhase, Severity
from status.models import ComponentStatus, EventUpdate, ServiceEvent

# Worse than this and nothing is wrong. Severity 3 is our own poll
# failing to read their page. Severity 4 is a window a provider always
# announces. Neither is an outage of theirs to report.
SYSTEM_EVENT_MAX_SEVERITY = Severity.DEGRADED

# Which severities end one of ours. Not the inverse of the rule above,
# on purpose. Unknown is absent because it is our own poll failing. A
# page we cannot read is no account of a recovery. Maintenance closes
# because a window a provider announces supersedes what we saw.
SYSTEM_EVENT_CLOSING_SEVERITIES = frozenset(
    {Severity.OPERATIONAL, Severity.MAINTENANCE}
)


def reconcile_system_events(service, author):
    """Open, extend and close the events this deployment owns."""
    for span in _bad_statuses(service):
        _open_or_extend(span, author)
    _close_recovered(service, author)


def _bad_statuses(service):
    """Open spans bad enough to be somebody's outage."""
    return ComponentStatus.objects.filter(
        component__service=service,
        ended_at__isnull=True,
        severity__lte=SYSTEM_EVENT_MAX_SEVERITY,
    ).select_related("component")


def _explained(component):
    """Whether a live provider event already accounts for this component.

    An incident that names no component covers its whole service. A
    provider publishes one for an outage that reaches everything. One
    outage is one card, so ours does not open beside it.

    A maintenance window naming nothing covers nothing. Planned work is
    no account of an outage. Read as one, it hides every outage that
    runs beside a window.
    """
    live = ServiceEvent.objects.live().filter(detected_by=EventSource.PROVIDER)
    if live.filter(affected_components=component).exists():
        return True
    return live.filter(
        service=component.service,
        kind=EventKind.INCIDENT,
        affected_components__isnull=True,
    ).exists()


def _ours(component):
    """The open event we opened for this component, if there is one."""
    return (
        ServiceEvent.objects.live()
        .filter(affected_components=component, detected_by=EventSource.SYSTEM)
        .first()
    )


def _open_or_extend(span, author):
    component = span.component
    if _explained(component):
        return
    event = _ours(component)
    if event is None:
        event = ServiceEvent.objects.create(
            service=component.service,
            external_id=None,
            detected_by=EventSource.SYSTEM,
            kind=EventKind.INCIDENT,
            title=_title(component, span.severity),
            phase=IncidentPhase.DETECTED,
            starts_at=span.started_at,
            created_by=author,
            updated_by=author,
        )
        event.affected_components.set([component])
    _record(event, span, author)


def _record(event, span, author):
    """One update per severity span, keyed on when the span began.

    A poll that changes nothing runs this again. `get_or_create` on the
    span's start is what stops a duplicate post per beat.
    """
    EventUpdate.objects.get_or_create(
        event=event,
        posted_at=span.started_at,
        defaults={
            "phase": event.phase,
            "source": EventSource.SYSTEM,
            "body": _title(span.component, span.severity),
            "created_by": author,
            "updated_by": author,
        },
    )


def _close_recovered(service, author):
    """Close ours once the component it names is no longer bad."""
    open_events = ServiceEvent.objects.live().filter(
        service=service, detected_by=EventSource.SYSTEM
    )
    for event in open_events:
        component = event.affected_components.first()
        if component is None:
            continue
        current = ComponentStatus.objects.filter(
            component=component, ended_at__isnull=True
        ).first()
        if _recovered(current):
            _close(event, component, current, author)


def _recovered(current):
    """Whether the open span says the outage is over.

    Closing needs a severity that means recovery, not merely one above
    the threshold that opened the event. No open span closes it too.
    """
    if current is None:
        return True
    return current.severity in SYSTEM_EVENT_CLOSING_SEVERITIES


def _close(event, component, current, author):
    # A component with no open span has nothing wrong with it. The
    # provider stopped listing it, and the card still has to close.
    now = timezone.now()
    severity = current.severity if current is not None else Severity.OPERATIONAL
    EventUpdate.objects.create(
        event=event,
        posted_at=now,
        phase=IncidentPhase.RESOLVED,
        source=EventSource.SYSTEM,
        body=_title(component, severity),
        created_by=author,
        updated_by=author,
    )
    event.phase = IncidentPhase.RESOLVED
    event.ends_at = now
    event.updated_by = author
    event.save(update_fields=["phase", "ends_at", "updated_by"])


def _title(component, severity):
    """What the card says before a provider gives it a better name."""
    return f"{component.name} {Severity(severity).label.lower()}"
