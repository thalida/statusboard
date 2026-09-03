"""Events we open when a provider explains nothing.

A provider can move a component to Degraded and never write an
incident. An event-only feed would hide that outage, and the closed
`ComponentStatus` span is exposed nowhere else.

A provider often posts after our poll saw the change. `claim` folds
their event into ours, so one outage stays one card.

`ComponentStatus` stays the truth. An event here is a projection of it,
written by this module alone and rebuildable from nothing. That is what
keeps it from being a second answer to the same question.
"""

from django.conf import settings
from django.db import transaction
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


@transaction.atomic
def claim(provider_event, author):
    """Fold a provider's event into the one we opened for the same outage.

    A provider often posts minutes after our poll saw the change. Two
    rows would be two cards for one outage.

    The provider's row is deleted and ours takes its id, so the fact
    that we found it first survives. Deleting theirs rather than ours
    is what keeps `detected_by` meaningful.

    Atomic on its own. A failure between the delete and the save loses
    their row. Ours is then left without the id. The next poll writes
    their event again, and moves duplicate updates onto ours.
    """
    if provider_event.detected_by != EventSource.PROVIDER:
        return False
    # Only an incident claims. A claim copies their phase onto ours,
    # and a maintenance phase on an incident is invalid. A planned
    # window is also no account of the outage we found.
    if provider_event.kind != EventKind.INCIDENT:
        return False
    ours = _claimable(provider_event)
    if ours is None:
        return False
    ours.external_id = provider_event.external_id
    ours.title = provider_event.title
    ours.phase = provider_event.phase
    ours.ends_at = provider_event.ends_at
    ours.updated_by = author
    # Their timeline moves first. A delete cascades to their updates,
    # so the other order loses every post they made.
    provider_event.updates.update(event=ours)
    ours.affected_components.add(*provider_event.affected_components.all())
    # The unique key is the service and the provider id. Ours cannot
    # hold their id while their row still does, so the save is last.
    provider_event.delete()
    ours.save(update_fields=["external_id", "title", "phase", "ends_at", "updated_by"])
    return True


def _claimable(provider_event):
    """Our open event for the same outage, or nothing.

    A candidate is on the same service and names one of their
    components. It began no later than their start plus the window.
    The candidate whose start is nearest theirs wins when several match.
    """
    components = list(provider_event.affected_components.all())
    if not components:
        return None
    # Read as "ours began no later than theirs plus the window". That
    # is the same rule as "theirs began no earlier than ours less it".
    floor = provider_event.starts_at + settings.EVENT_CLAIM_WINDOW
    candidates = (
        ServiceEvent.objects.live()
        .filter(
            service=provider_event.service,
            detected_by=EventSource.SYSTEM,
            external_id__isnull=True,
            affected_components__in=components,
            starts_at__lte=floor,
        )
        .distinct()
    )
    return min(
        candidates,
        key=lambda e: abs(e.starts_at - provider_event.starts_at),
        default=None,
    )


def _bad_statuses(service):
    """Open spans bad enough to be somebody's outage.

    An archived component is left out. Its last span stays open for
    good, so each poll would open a card that closes in the same pass.
    """
    return ComponentStatus.objects.filter(
        component__service=service,
        component__is_archived=False,
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
    """Close ours once every component it names is no longer bad."""
    open_events = ServiceEvent.objects.live().filter(
        service=service, detected_by=EventSource.SYSTEM
    )
    for event in open_events:
        closing = _closing(event)
        if closing is not None:
            _close(event, author, *closing)


def _closing(event):
    """When and why an event ends, or nothing while a component is bad.

    A claim merges the provider's components onto ours, and they name
    several. One recovery is no account of the others.

    The component that settles last decides both. Holding the card open
    until then is the conservative error. Closing early leaves a
    component down with nothing covering it. The next poll then opens a
    second card for the same outage.
    """
    now = timezone.now()
    # The primary key sorts by creation, so this is a total order. The
    # relation has none, and the pair below has to be repeatable.
    components = list(event.affected_components.order_by("pk"))
    if not components:
        return None
    settled = []
    for component in components:
        ended = _settled(component, now)
        if ended is None:
            return None
        settled.append(ended)
    return max(settled, key=lambda pair: pair[0])


def _settled(component, now):
    """When and why one component stopped being bad, or nothing."""
    # A provider stopped publishing an archived component. Nothing can
    # report its recovery, so the event would never close.
    if component.is_archived:
        return component.archived_at, f"{component.name} is no longer published"
    current = ComponentStatus.objects.filter(
        component=component, ended_at__isnull=True
    ).first()
    if not _recovered(current):
        return None
    # A component with no open span has nothing wrong with it.
    severity = current.severity if current is not None else Severity.OPERATIONAL
    return now, _title(component, severity)


def _recovered(current):
    """Whether the open span says the outage is over.

    Closing needs a severity that means recovery, not merely one above
    the threshold that opened the event. No open span closes it too.
    """
    if current is None:
        return True
    return current.severity in SYSTEM_EVENT_CLOSING_SEVERITIES


def _close(event, author, ends_at, body):
    """Resolve one of ours, and post the update that says why."""
    EventUpdate.objects.create(
        event=event,
        posted_at=ends_at,
        phase=IncidentPhase.RESOLVED,
        source=EventSource.SYSTEM,
        body=body,
        created_by=author,
        updated_by=author,
    )
    event.phase = IncidentPhase.RESOLVED
    event.ends_at = ends_at
    event.updated_by = author
    event.save(update_fields=["phase", "ends_at", "updated_by"])


def _title(component, severity):
    """What the card says before a provider gives it a better name."""
    return f"{component.name} {Severity(severity).label.lower()}"
