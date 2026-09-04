"""Build a whole service by reading its status page.

An import is a poll that somebody asked for, so it belongs with the
machinery that polls.

It was a manager method on Service. That made `catalog.models` reach
into `polling` for an adapter, a run and a reconcile. Each of those
imports had to be deferred, or the two apps imported each other while
loading.

The direction is one way now. `polling` imports `catalog`, because a
poller is machinery about a service. `catalog.models` reaches back only
once, in `ensure_poller`, which says why.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from catalog.choices import ServiceSource
from catalog.models import Service, StatusPage
from polling.adapters.registry import identify
from polling.models import PollRun
from polling.reconcile import apply_fetch

# What `author` means when a caller passes nothing. A scheduled job
# and a management command sign their rows with the system account.
# `None` is a different answer: a person we cannot name.
AUTOMATED = object()


def import_from_url(url: str, author=AUTOMATED) -> tuple[Service, bool]:
    """Build a whole service from a status page URL.

    The provider, the name, the components and the event history all
    come from the page. Returns (service, created); importing a page
    that is already in the catalog returns the existing service.

    `author` signs the service and its status page. A request path
    passes the caller, so the admin who imported Twilio is on the row.
    It falls back to the system account, which is true of a command.

    Reading and writing are two steps, and only the write is a
    transaction. A provider takes seconds to answer, and a database
    connection must not spend them waiting on one.

    """
    if author is AUTOMATED:
        author = get_user_model().objects.system()
    key = StatusPage.normalise_url(url)
    already = _imported(key)
    if already is not None:
        return already, False

    adapter_class, fetch_url = identify(key)
    adapter = adapter_class(fetch_url)
    started = timezone.now()
    fetched = {
        "metadata": adapter.named_metadata(),
        "logo": adapter.fetch_logo(),
        "components": adapter.fetch_status(),
        "events": adapter.fetch_incidents(),
        "source": adapter.status_source,
        "started": started,
    }
    return _import(key, adapter_class, fetch_url, fetched, author)


def _imported(key):
    """The service this page already belongs to, if any."""
    page = StatusPage.objects.filter(url=key).select_related("service").first()
    return page.service if page is not None else None


@transaction.atomic
def _import(key, adapter_class, fetch_url, fetched, author):
    """Write what the page said, in one transaction."""
    # Somebody may have imported the same page while we read it. The
    # fetch is outside the transaction now, so that window is
    # seconds wide rather than none.
    already = _imported(key)
    if already is not None:
        return already, False

    metadata = fetched["metadata"]
    service = Service.objects.create(
        name=metadata["name"],
        homepage_url=metadata.get("homepage_url", ""),
        logo=fetched["logo"],
        source=ServiceSource.IMPORT,
        created_by=author,
        updated_by=author,
    )
    StatusPage.objects.create(
        service=service,
        created_by=author,
        updated_by=author,
        url=key,
        provider=adapter_class.provider,
        # Set when the page's own address is not what we read.
        # A page whose feed lives at its own path, for one.
        api_url_override="" if fetch_url == key else fetch_url,
    )
    # An import is a fetch, so it is recorded as one. Without it
    # the first reading has no provenance, and the log is missing
    # the request that made the rows.
    #
    # Nothing above makes the poller. `Service.ensure_poller` does, on
    # the save. Making one here would trip the one-to-one column.
    run = PollRun.open(
        service.poller, key, adapter_class.provider, at=fetched["started"]
    )
    apply_fetch(
        service,
        fetched["components"],
        fetched["events"],
        fetched["source"],
        run,
    )
    # An import is a successful poll, so the run closes as one and
    # the poller moves on. Left alone, a freshly imported service
    # read "never polled" until the first tick.
    run.finish(ok=True)
    return service, True
