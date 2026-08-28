from datetime import timedelta
from urllib.parse import urlparse, urlunparse

from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from common.models import BaseModel


class ServiceManager(models.Manager):
    @transaction.atomic
    def import_from_url(self, url: str) -> tuple["Service", bool]:
        """Build a whole service from a status page URL.

        The provider, the name, the components and the event history all
        come from the page. Returns (service, created); importing a page
        that is already in the catalog returns the existing service.

        The polling imports are local to the method. `polling` imports
        this module, so a top-level import would close the loop.
        """
        from django.contrib.auth import get_user_model

        from polling.adapters.registry import identify
        from polling.models import PollRun
        from polling.reconcile import apply_fetch
        from status.choices import StatusSource

        key = StatusPage.normalise_url(url)
        existing = StatusPage.objects.filter(url=key).select_related("service").first()
        if existing is not None:
            return existing.service, False

        adapter_class, fetch_url = identify(key)
        adapter = adapter_class(fetch_url)
        metadata = adapter.fetch_service_metadata()

        # Nobody typed these in, so they are signed by the system account
        # rather than left blank.
        author = get_user_model().objects.system()
        service = self.create(
            name=metadata.get("name") or urlparse(key).netloc,
            description=metadata.get("description", ""),
            homepage_url=metadata.get("homepage_url", ""),
            logo=adapter.fetch_logo(),
            created_by=author,
            updated_by=author,
        )
        StatusPage.objects.create(
            service=service,
            created_by=author,
            updated_by=author,
            url=key,
            provider=adapter_class.provider,
            # Set when the page's own address is not what we read: a
            # page whose feed lives at a path of its own, for one.
            api_url_override="" if fetch_url == key else fetch_url,
        )
        # The Poller comes from the Service signal; one here would duplicate it.

        # An import is a fetch, so it is recorded as one. Without this the
        # first reading of every service has no provenance, and the poll
        # log is missing the request that created the rows.
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
            created_by=author,
            updated_by=author,
        )
        apply_fetch(
            service,
            components,
            events,
            getattr(adapter, "status_source", StatusSource.PROVIDER),
            run,
        )

        # An import is a successful poll, so the poller records one. Left
        # alone, a freshly imported service read "never polled" on every
        # screen until the first scheduled tick.
        poller = service.poller
        poller.last_success_at = run.finished_at
        poller.next_at = run.finished_at + timedelta(
            seconds=poller.effective_interval_seconds
        )
        poller.save(update_fields=["last_success_at", "next_at"])
        return service, True


class Service(BaseModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(
        unique=True,
        blank=True,
        help_text="Derived from the name when left blank.",
    )
    description = models.TextField(blank=True, default="")
    logo = models.URLField(blank=True, default="")
    homepage_url = models.URLField(blank=True, default="")
    is_featured = models.BooleanField(verbose_name="Featured", default=False)
    # Derived. Never set by hand: it decides what gets polled.
    watcher_count = models.PositiveIntegerField(
        verbose_name="Watchers", default=0, editable=False
    )

    objects = ServiceManager()

    history = HistoricalRecords()

    def refresh_watcher_count(self):
        """Recount the distinct users tracking any part of this service.

        Distinct users, not items. Someone tracking five Twilio components
        is one watcher, and a counter incremented per item would let one
        person outrank a crowd in the suggestion order.
        """
        from django.contrib.auth import get_user_model

        Service.objects.filter(pk=self.pk).update(
            watcher_count=get_user_model()
            .objects.filter(dashboards__items__component__service=self)
            .distinct()
            .count()
        )

    def save(self, *args, **kwargs):
        # Only on the way in. The slug is the public URL of a service, so
        # a later rename must not move it.
        if not self.slug:
            self.slug = unique_slug(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


def unique_slug(name):
    """A slug from the name, with a counter if it is taken.

    Two providers really can share a name, so this cannot just fail.
    """
    base = slugify(name) or "service"
    slug, suffix = base, 1
    while Service.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


class StatusPage(BaseModel):
    service = models.OneToOneField(
        Service, on_delete=models.CASCADE, related_name="status_page"
    )
    url = models.URLField(unique=True)
    provider = models.CharField(max_length=32, choices=StatusPageProvider.choices)
    # An override, not a derived value. Each adapter works out its own API
    # path from `url` — Statuspage joins "api/v2/summary.json" onto it — so
    # nothing is stored for the normal case. Set this only when that join
    # lands somewhere wrong, such as a page served on one domain whose API
    # lives on another.
    api_url_override = models.URLField(
        null=True,
        blank=True,
        help_text="Leave blank. Set only when the adapter cannot reach the "
        "API by joining a path onto the page URL.",
    )

    history = HistoricalRecords()

    @staticmethod
    def normalise_url(url: str) -> str:
        """The dedupe key, and the URL every poll is built from.

        It is both, which is why `www.` is kept. Stripping it made a
        tidier key and an unfetchable address: githubstatus.com redirects
        to the www root page, so joining "api/v2/summary.json" onto the
        stripped host returned the HTML homepage instead of the summary.

        The cost is that www.example.com and example.com import as two
        services. That is a duplicate row. Dropping the prefix was a
        service that could never be polled at all.
        """
        parts = urlparse(url.strip())
        return urlunparse(
            (
                parts.scheme or "https",
                parts.netloc.lower(),
                parts.path.rstrip("/"),
                "",
                "",
                "",
            )
        )


class ServiceComponent(BaseModel):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="components"
    )
    name = models.CharField(max_length=200)
    external_id = models.CharField(verbose_name="Provider ID", max_length=200)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    status_page_order = models.IntegerField(verbose_name="Page order", default=0)
    is_overall = models.BooleanField(verbose_name="Overall", default=False)
    archived_at = models.DateTimeField(verbose_name="Archived", null=True, blank=True)

    history = HistoricalRecords()

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["service", "external_id"], name="one_component_per_provider_id"
            ),
            models.UniqueConstraint(
                fields=["service"],
                condition=models.Q(is_overall=True),
                name="one_overall_component_per_service",
            ),
        ]

    @property
    def ancestors(self):
        """The components above this one, top down.

        A provider can nest a component under another. The chain is what
        tells you where it sits on the status page. The guard is for bad
        data: the column points at its own table, so a loop is possible.
        """
        chain, node, seen = [], self.parent, {self.pk}
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    @property
    def path(self):
        """Where the component sits, read from the service down."""
        names = [self.service.name, *(a.name for a in self.ancestors), self.name]
        return " / ".join(names)

    def __str__(self):
        return self.path
