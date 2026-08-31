from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from catalog.models import Service
from common.ordering import is_tracked
from polling.adapters.registry import for_provider
from polling.models import Poller, PollRun
from polling.reconcile import apply_fetch


def active_pollers():
    """The pollers this deployment actually runs.

    Nothing else is ever dispatched, so nothing else can be late or
    stale. Anything reporting on polling reads this, or it reports on
    pollers that were never going to run.
    """
    return Poller.objects.filter(
        is_tracked("service_id"),
        service__status_page__isnull=False,
        is_paused=False,
    )


def due_pollers():
    """Active pollers past next_at."""
    now = timezone.now()
    return (
        active_pollers()
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
    poller = getattr(service, "poller", None)
    page = getattr(service, "status_page", None)
    if poller is None or page is None:
        # Nothing to read and nowhere to record it. A PollRun needs the
        # page's url and provider, so there is not even a row to write.
        return
    # A run is the top of the trail. Nothing above it says where it
    # came from, so it signs itself.
    run = PollRun.open(poller, page.url, page.provider)
    failure = None
    try:
        adapter = for_provider(page.provider)(page.api_url_override or page.url)
        components = adapter.fetch_status()
        events = adapter.fetch_incidents()
        metadata = adapter.fetch_service_metadata()
        apply_fetch(service, components, events, adapter.status_source, run)
        _refresh_metadata(service, metadata, adapter)
    except Exception as error:  # noqa: BLE001 — every failure is recorded, never raised away
        # A failed fetch keeps the last known value.
        # `apply_fetch` does not run, so the open rows stand.
        failure = error
    finally:
        run.finish(ok=failure is None, error=failure)


def _refresh_metadata(service, metadata, adapter=None):
    """A rename upstream must not leave a stale name on someone's board.

    The logo is fetched only when missing. It is a second request
    against the provider. Doing it every poll would double the traffic,
    to read something that almost never changes.
    """
    changed = []
    if adapter is not None and not service.logo:
        logo = adapter.fetch_logo()
        if logo:
            service.logo = logo
            changed.append("logo")
    for field in ("name", "description", "homepage_url"):
        value = metadata.get(field)
        if value and getattr(service, field) != value:
            setattr(service, field, value)
            changed.append(field)
    if changed:
        service.save(update_fields=changed)
