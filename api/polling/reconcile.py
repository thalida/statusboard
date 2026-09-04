from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from catalog.models import ServiceComponent
from polling.system_events import claim, reconcile_system_events
from status.models import ComponentStatus, EventUpdate, ServiceEvent


@transaction.atomic
def apply_fetch(service, components, events, source, run=None):
    """Write one adapter fetch to the database.

    A poll is a reconciliation, not a status read.
    Components upsert on `external_id`. Vanished ones archive.
    An unchanged severity leaves the open status row alone.

    `run` is the PollRun that produced this data. Stamping it makes a
    reading traceable back to the fetch that wrote it.

    Nobody types any of this, so the system account signs every row. A
    blank author reads the same as one that was lost, and a component
    carries no run to say otherwise.
    """
    # A poll writes to the service it read. Nothing in the arguments
    # ties them together. A run from another poller would file one
    # service's readings under another.
    if run is not None and run.poller.service_id != service.pk:
        raise ValueError(
            f"{run} polled {run.poller.service}, not {service}. "
            "A poll writes to the service it read."
        )
    author = get_user_model().objects.system()
    rows = _upsert_components(service, components, author)
    _archive_vanished(service, components, author)
    _write_statuses(components, rows, source, author, run)
    _upsert_events(service, events, rows, author, run)
    # After the provider's events, so a component they explained does
    # not also get one of ours in the same pass.
    reconcile_system_events(service, author)


def _signed(author, **fields):
    """The same fields, for an update and for a create.

    `update_or_create` cannot tell the two apart. A row records who
    made it once, not again on every poll.
    """
    return {
        "defaults": {**fields, "updated_by": author},
        "create_defaults": {**fields, "created_by": author, "updated_by": author},
    }


def _upsert_components(service, components, author):
    rows = {}
    for incoming in components:
        row, _ = ServiceComponent.objects.update_or_create(
            service=service,
            external_id=incoming.external_id,
            **_signed(
                author,
                name=incoming.name,
                status_page_order=incoming.order,
                is_overall=incoming.is_overall,
                is_archived=False,
                archived_at=None,
            ),
        )
        rows[incoming.external_id] = row

    # Parents second: a child may arrive before its parent exists.
    for incoming in components:
        parent = (
            rows.get(incoming.parent_external_id)
            if incoming.parent_external_id
            else None
        )
        row = rows[incoming.external_id]
        if row.parent_id != (parent.id if parent else None):
            row.parent = parent
            row.updated_by = author
            row.save(update_fields=["parent", "updated_by"])
    return rows


def _archive_vanished(service, components, author):
    seen = {c.external_id for c in components}
    # A bulk update never reaches `save`, so both columns are written
    # here. The constraint refuses the pair if they ever come apart.
    ServiceComponent.objects.filter(service=service, is_archived=False).exclude(
        external_id__in=seen
    ).update(is_archived=True, archived_at=timezone.now(), updated_by=author)


def _write_statuses(components, rows, source, author, run=None):
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
            current.updated_by = author
            current.save(update_fields=["ended_at", "updated_by"])
        ComponentStatus.objects.create(
            component=row,
            severity=incoming.severity,
            source=source,
            started_at=now,
            poll_run=run,
            created_by=author,
            updated_by=author,
        )


def _affected(service, rows, external_ids):
    """The components an event names, as rows of this service.

    `rows` holds only what this fetch described. Read from it alone, an
    event lost its link to any component the provider stopped listing.
    So anything missing is looked up among the service's own components,
    archived ones included.

    Nothing is created. A component the provider never described is one
    we invented. It would show on the catalog and on boards as though
    the provider published it. An id that matches nothing is dropped,
    and the event is still recorded against the service.
    """
    named = [rows[e] for e in external_ids if e in rows]
    unknown = [e for e in external_ids if e not in rows]
    if unknown:
        named += list(
            ServiceComponent.objects.filter(service=service, external_id__in=unknown)
        )
    return named


def _upsert_events(service, events, rows, author, run=None):
    for incoming in events:
        event, _ = ServiceEvent.objects.update_or_create(
            service=service,
            external_id=incoming.external_id,
            **_signed(
                author,
                kind=incoming.kind,
                title=incoming.title,
                phase=incoming.phase,
                starts_at=incoming.starts_at,
                ends_at=incoming.ends_at,
                poll_run=run,
            ),
        )
        event.affected_components.set(
            _affected(service, rows, incoming.affected_external_ids)
        )
        for update in incoming.updates:
            EventUpdate.objects.get_or_create(
                event=event,
                posted_at=update.posted_at,
                defaults={
                    "phase": update.phase,
                    "body": update.body,
                    "created_by": author,
                    "updated_by": author,
                },
            )
        # After the updates, so they move with the row if this event
        # takes over one we opened.
        claim(event, author)
