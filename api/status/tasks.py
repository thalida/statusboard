import random
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from catalog.adapters.registry import detect
from catalog.models import Poller, Service
from catalog.reconcile import apply_fetch
from status.choices import StatusSource
from status.models import PollRun

JITTER = 0.1


def next_interval_seconds(base, failures, ceiling):
    """Exponential backoff.

    A service in backoff is not checked every five minutes.
    The service screen shows this interval, not the deployment default.
    """
    return min(base * (2**failures), ceiling)


def due_pollers():
    """Only services someone tracks, not paused, and past next_at."""
    now = timezone.now()
    return (
        Poller.objects.filter(service__watcher_count__gt=0, is_paused=False)
        .filter(Q(next_at__isnull=True) | Q(next_at__lte=now))
        .select_related("service")
        .order_by("next_at")
    )


@shared_task
def enqueue_due_polls():
    for poller in due_pollers():
        poll_service.delay(str(poller.service_id))


@shared_task
def poll_service(service_id):
    service = Service.objects.select_related("status_page", "poller").get(id=service_id)
    poller = service.poller
    page = service.status_page
    run = PollRun.objects.create(
        poller=poller, url=page.url, provider=page.provider, started_at=timezone.now()
    )
    try:
        adapter = detect(page.url)(page.api_url or page.url)
        components = adapter.fetch_status()
        events = adapter.fetch_incidents()
        metadata = adapter.fetch_service_metadata()
        source = getattr(adapter, "status_source", StatusSource.PROVIDER)
        apply_fetch(service, components, events, source)
        _refresh_metadata(service, metadata)
    except Exception as error:  # noqa: BLE001 — every failure is recorded, never raised away
        # A failed fetch keeps the last known value.
        # `apply_fetch` does not run, so the open rows stand.
        poller.consecutive_failure_count += 1
        run.ok, run.error = False, str(error)
    else:
        poller.consecutive_failure_count = 0
        poller.last_success_at = timezone.now()
        run.ok = True
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["ok", "error", "finished_at"])
        seconds = next_interval_seconds(
            poller.effective_interval_seconds,
            poller.consecutive_failure_count,
            poller.effective_max_interval_seconds,
        )
        # Jitter so a hundred services do not stampede one provider on the minute.
        seconds *= 1 + random.uniform(-JITTER, JITTER)
        poller.next_at = timezone.now() + timedelta(seconds=seconds)
        poller.save(
            update_fields=["consecutive_failure_count", "last_success_at", "next_at"]
        )


def _refresh_metadata(service, metadata):
    """A rename upstream must not leave a stale name on someone's board."""
    changed = []
    for field in ("name", "description", "homepage_url"):
        value = metadata.get(field)
        if value and getattr(service, field) != value:
            setattr(service, field, value)
            changed.append(field)
    if changed:
        service.save(update_fields=changed)
