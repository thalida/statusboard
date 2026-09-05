from django.db import models


class Severity(models.IntegerChoices):
    MAJOR_OUTAGE = 0, "Major outage"
    PARTIAL_OUTAGE = 1, "Partial outage"
    DEGRADED = 2, "Degraded"
    UNKNOWN = 3, "Unknown"
    MAINTENANCE = 4, "Maintenance"
    OPERATIONAL = 5, "Operational"


class StatusSource(models.TextChoices):
    """Where a severity came from.

    The field's help text says what each one means. A label is read in a
    column and has to fit one.
    """

    PROVIDER = "provider", "Provider"
    COMPONENTS = "components", "Components"
    INCIDENTS = "incidents", "Incidents"


class EventKind(models.TextChoices):
    INCIDENT = "incident", "Incident"
    MAINTENANCE = "maintenance", "Maintenance"


class IncidentPhase(models.TextChoices):
    # First, because it precedes anything a provider posts. We write it
    # when a severity drops with nothing explaining it.
    DETECTED = "detected", "Detected"
    INVESTIGATING = "investigating", "Investigating"
    IDENTIFIED = "identified", "Identified"
    MONITORING = "monitoring", "Monitoring"
    RESOLVED = "resolved", "Resolved"


class MaintenancePhase(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    VERIFYING = "verifying", "Verifying"
    COMPLETED = "completed", "Completed"


class EventSource(models.TextChoices):
    """Who produced a row: the provider's page, or this deployment.

    An event records who opened it. An update records who wrote it. A
    claimed event has both, one per update.
    """

    PROVIDER = "provider", "Provider"
    SYSTEM = "system", "Statusboard"


class EventPhaseState(models.TextChoices):
    """Whether an event is still running, or over.

    The `phase=` filter takes one of these. `CLOSED_PHASES` below draws
    the line and stays on the server, so a client never restates which
    phases are terminal. These two labels are what a client shows, so
    `/meta/` publishes them beside every other fixed set.
    """

    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


EVENT_PHASES_BY_KIND = {
    EventKind.INCIDENT: IncidentPhase,
    EventKind.MAINTENANCE: MaintenancePhase,
}

# A closed phase means the event is over. All other phases are open.
CLOSED_PHASES = frozenset({IncidentPhase.RESOLVED, MaintenancePhase.COMPLETED})
OPEN_INCIDENT_PHASES = frozenset(set(IncidentPhase) - CLOSED_PHASES)
