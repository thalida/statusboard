import random
import sys
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from catalog.models import Service
from common.ordering import is_tracked
from polling.adapters.registry import for_provider
from polling.models import Poller, PollRun
from polling.reconcile import apply_fetch
from status.choices import StatusSource

JITTER = 0.1


def next_interval_seconds(base, failures, ceiling):
    """Exponential backoff.

    A service in backoff is not checked every five minutes.
    The service screen shows this interval, not the deployment default.
    """
    return min(base * (2**failures), ceiling)


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


def exception_name(error):
    """The name that identifies a failure.

    Wrappers stack: `requests.ConnectionError` over urllib3's
    `MaxRetryError` over `NameResolutionError` over `socket.gaierror`.
    The outermost says "the network", the innermost says "errno". The
    deepest one a library defines is the one that names the cause.
    """
    name = type(error).__name__
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        module = type(error).__module__.partition(".")[0]
        if module != "builtins" and module not in sys.stdlib_module_names:
            name = type(error).__name__
        error = error.__cause__ or error.__context__
    return name


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
    author = get_user_model().objects.system()
    run = PollRun.objects.create(
        poller=poller,
        url=page.url,
        provider=page.provider,
        started_at=timezone.now(),
        created_by=author,
        updated_by=author,
    )
    try:
        adapter = for_provider(page.provider)(page.api_url_override or page.url)
        components = adapter.fetch_status()
        events = adapter.fetch_incidents()
        metadata = adapter.fetch_service_metadata()
        source = getattr(adapter, "status_source", StatusSource.PROVIDER)
        apply_fetch(service, components, events, source, run)
        _refresh_metadata(service, metadata, adapter)
    except Exception as error:  # noqa: BLE001 — every failure is recorded, never raised away
        # A failed fetch keeps the last known value.
        # `apply_fetch` does not run, so the open rows stand.
        poller.consecutive_failure_count += 1
        run.ok, run.error = False, str(error)
        run.error_type = exception_name(error)
    else:
        poller.consecutive_failure_count = 0
        poller.last_success_at = timezone.now()
        run.ok = True
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["ok", "error", "error_type", "finished_at"])
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
