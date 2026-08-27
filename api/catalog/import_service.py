from urllib.parse import urlparse, urlunparse

from django.db import transaction
from django.utils.text import slugify

from catalog.adapters.registry import detect
from catalog.models import Poller, Service, StatusPage
from catalog.reconcile import apply_fetch
from status.choices import StatusSource


def normalise(url: str) -> str:
    """The dedupe key. One status page gives one service and one poll."""
    parts = urlparse(url.strip())
    scheme = parts.scheme or "https"
    netloc = parts.netloc.lower().removeprefix("www.")
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
        slug=_unique_slug(name),
        name=name,
        description=metadata.get("description", ""),
        homepage_url=metadata.get("homepage_url", ""),
    )
    StatusPage.objects.create(service=service, url=key, provider=adapter_class.provider)
    Poller.objects.create(service=service)

    apply_fetch(
        service,
        adapter.fetch_status(),
        adapter.fetch_incidents(),
        getattr(adapter, "status_source", StatusSource.PROVIDER),
    )
    return service, True


def _unique_slug(name):
    base = slugify(name) or "service"
    slug, n = base, 1
    while Service.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug
