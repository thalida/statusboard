from django.db import transaction
from django.utils import timezone

from catalog.models import ServiceComponent
from status.models import ComponentStatus, EventUpdate, ServiceEvent


@transaction.atomic
def apply_fetch(service, components, events, source):
    """Write one adapter fetch to the database.

    A poll is a reconciliation, not a status read.
    Components upsert on `external_id`. Vanished ones archive.
    An unchanged severity leaves the open status row alone.
    """
    rows = _upsert_components(service, components)
    _archive_vanished(service, components)
    _write_statuses(components, rows, source)
    _upsert_events(service, events, rows)


def _upsert_components(service, components):
    rows = {}
    for incoming in components:
        row, _ = ServiceComponent.objects.update_or_create(
            service=service,
            external_id=incoming.external_id,
            defaults={
                "name": incoming.name,
                "status_page_order": incoming.order,
                "is_overall": incoming.is_overall,
                "archived_at": None,
            },
        )
        rows[incoming.external_id] = row

    # Parents in a second pass: a child may arrive before its parent exists.
    for incoming in components:
        parent = (
            rows.get(incoming.parent_external_id)
            if incoming.parent_external_id
            else None
        )
        row = rows[incoming.external_id]
        if row.parent_id != (parent.id if parent else None):
            row.parent = parent
            row.save(update_fields=["parent"])
    return rows


def _archive_vanished(service, components):
    seen = {c.external_id for c in components}
    ServiceComponent.objects.filter(service=service, archived_at__isnull=True).exclude(
        external_id__in=seen
    ).update(archived_at=timezone.now())


def _write_statuses(components, rows, source):
    now = timezone.now()
    for incoming in components:
        row = rows[incoming.external_id]
        current = ComponentStatus.objects.filter(
            component=row, ended_at__isnull=True
        ).first()
        if current is not None and current.severity == incoming.severity:
            continue
        if current is not None:
            current.ended_at = now
            current.save(update_fields=["ended_at"])
        ComponentStatus.objects.create(
            component=row, severity=incoming.severity, source=source, started_at=now
        )


def _upsert_events(service, events, rows):
    for incoming in events:
        event, _ = ServiceEvent.objects.update_or_create(
            service=service,
            external_id=incoming.external_id,
            defaults={
                "kind": incoming.kind,
                "title": incoming.title,
                "phase": incoming.phase,
                "starts_at": incoming.starts_at,
                "ends_at": incoming.ends_at,
            },
        )
        named = [rows[e] for e in incoming.affected_external_ids if e in rows]
        event.affected_components.set(named)
        for update in incoming.updates:
            EventUpdate.objects.get_or_create(
                event=event,
                posted_at=update.posted_at,
                defaults={"phase": update.phase, "body": update.body},
            )
