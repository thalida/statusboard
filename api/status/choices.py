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
    INVESTIGATING = "investigating", "Investigating"
    IDENTIFIED = "identified", "Identified"
    MONITORING = "monitoring", "Monitoring"
    RESOLVED = "resolved", "Resolved"


class MaintenancePhase(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    VERIFYING = "verifying", "Verifying"
    COMPLETED = "completed", "Completed"


EVENT_PHASES_BY_KIND = {
    EventKind.INCIDENT: IncidentPhase,
    EventKind.MAINTENANCE: MaintenancePhase,
}

# A closed phase means the event is over. All other phases are open.
CLOSED_PHASES = frozenset({IncidentPhase.RESOLVED, MaintenancePhase.COMPLETED})
OPEN_INCIDENT_PHASES = frozenset(set(IncidentPhase) - CLOSED_PHASES)
