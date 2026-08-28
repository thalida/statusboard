from urllib.parse import urlparse, urlunparse

from django.db import transaction
from django.utils import timezone

from catalog.models import Service, StatusPage
from polling.adapters.registry import detect
from polling.models import PollRun
from polling.reconcile import apply_fetch
from status.choices import StatusSource


def normalise(url: str) -> str:
    """The dedupe key, and the URL every poll is built from.

    It is both, which is why `www.` is kept. Stripping it made a tidier
    key and an unfetchable address: githubstatus.com redirects to the www
    root page, so joining "api/v2/summary.json" onto the stripped host
    returned the HTML homepage instead of the summary.

    The cost is that www.example.com and example.com import as two
    services. That is a duplicate row. Dropping the prefix was a service
    that could never be polled at all.
    """
    parts = urlparse(url.strip())
    scheme = parts.scheme or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", "", ""))


@transaction.atomic
def import_from_url(url: str) -> tuple[Service, bool]:
    key = normalise(url)
    existing = StatusPage.objects.filter(url=key).select_related("service").first()
    if existing is not None:
        return existing.service, False

    adapter_class = detect(key)
    adapter = adapter_class(key)
    metadata = adapter.fetch_service_metadata()
    name = metadata.get("name") or urlparse(key).netloc

    service = Service.objects.create(
        name=name,
        description=metadata.get("description", ""),
        homepage_url=metadata.get("homepage_url", ""),
    )
    StatusPage.objects.create(service=service, url=key, provider=adapter_class.provider)
    # The Poller comes from the Service signal; creating one here duplicates it.

    # An import is a fetch, so it is recorded as one. Without this the
    # first reading of every service has no provenance, and the poll log
    # is missing the request that actually created the rows.
    started = timezone.now()
    components = adapter.fetch_status()
    events = adapter.fetch_incidents()
    run = PollRun.objects.create(
        poller=service.poller,
        url=key,
        provider=adapter_class.provider,
        started_at=started,
        finished_at=timezone.now(),
        ok=True,
    )
    apply_fetch(
        service,
        components,
        events,
        getattr(adapter, "status_source", StatusSource.PROVIDER),
        run,
    )
    return service, True
