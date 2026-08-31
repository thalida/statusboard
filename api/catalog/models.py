from urllib.parse import urlparse, urlunparse

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from common.models import BaseModel


class ServiceManager(models.Manager):
    def import_from_url(self, url: str) -> tuple["Service", bool]:
        """Build a whole service from a status page URL.

        The provider, the name, the components and the event history all
        come from the page. Returns (service, created); importing a page
        that is already in the catalog returns the existing service.

        Reading and writing are two steps, and only the write is a
        transaction. A provider takes seconds to answer, and a database
        connection must not spend them waiting on one.

        The polling imports are local to the method. `polling` imports
        this module, so a top-level import would close the loop.
        """
        from polling.adapters.registry import identify

        key = StatusPage.normalise_url(url)
        already = self._imported(key)
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
        return self._import(key, adapter_class, fetch_url, fetched)

    def _imported(self, key):
        """The service this page already belongs to, if any."""
        page = StatusPage.objects.filter(url=key).select_related("service").first()
        return page.service if page is not None else None

    @transaction.atomic
    def _import(self, key, adapter_class, fetch_url, fetched):
        """Write what the page said, in one transaction."""
        from django.contrib.auth import get_user_model

        from polling.models import PollRun
        from polling.reconcile import apply_fetch

        # Somebody may have imported the same page while we read it. The
        # fetch is outside the transaction now, so that window is
        # seconds wide rather than none.
        already = self._imported(key)
        if already is not None:
            return already, False

        metadata = fetched["metadata"]
        # Nobody typed these in, so they are signed by the system account
        # rather than left blank.
        author = get_user_model().objects.system()
        service = self.create(
            name=metadata["name"],
            description=metadata.get("description", ""),
            homepage_url=metadata.get("homepage_url", ""),
            logo=fetched["logo"],
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
        # Nothing above makes the poller. `create_poller` in
        # polling.signals does, on the Service save. Making one here
        # would trip the one-to-one column.
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
    objects = ServiceManager()

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Only on the way in. The slug is the public URL of a service, so
        # a later rename must not move it.
        if not self.slug:
            self.slug = unique_slug(self.name)
        new = self._state.adding
        super().save(*args, **kwargs)
        if new:
            self.ensure_poller()

    def ensure_poller(self):
        """Every service is polled, so every service has one.

        The Poller carries tuning only, and every field has a deployment
        default. There is nothing to ask for at creation time. A
        StatusPage cannot be made this way: it needs a URL, and there is
        no sensible default for one.

        A one-to-one is only a promise from the side that holds the
        column. Nothing in the database stops a service without one, so
        this is what keeps it true. A migration backfilled the rows that
        predate it.
        """
        from django.contrib.auth import get_user_model

        from polling.models import Poller

        # Nobody adds this one, so the system account signs it. A blank
        # author would read as one that was lost.
        author = get_user_model().objects.system()
        poller, _ = Poller.objects.get_or_create(
            service=self,
            defaults={"created_by": author, "updated_by": author},
        )
        return poller

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
    # An override, not a derived value. Each adapter works out its own
    # API path from `url`. Statuspage joins "api/v2/summary.json" onto
    # it, so nothing is stored for the normal case.
    #
    # Set this only when that join lands somewhere wrong. A page served
    # on one domain whose API lives on another, for one.
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
        tidier key and an unfetchable address. githubstatus.com
        redirects to the www root, so the joined path returned the HTML
        homepage.

        The cost is that www.example.com and example.com import twice.
        That is a duplicate row. Dropping the prefix was a service that
        could never be polled.
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
    # Archiving is the flag. The date is kept because `updated_at`
    # moves on every save, so a later rename would erase it. `save` sets
    # the date from the flag, and a constraint holds them together.
    #
    # `db_default` as well as `default`. The column is NOT NULL. A
    # writer that predates it, such as an old worker mid-deploy, omits
    # it and the insert fails. The database supplies it instead.
    is_archived = models.BooleanField(
        verbose_name="Archived", default=False, db_default=False
    )
    archived_at = models.DateTimeField(
        verbose_name="Archived on", null=True, blank=True, editable=False
    )

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
            models.CheckConstraint(
                condition=models.Q(is_archived=True, archived_at__isnull=False)
                | models.Q(is_archived=False, archived_at__isnull=True),
                name="archived_flag_and_date_agree",
            ),
        ]

    def save(self, *args, **kwargs):
        """Keep the archive date in step with the flag.

        A bulk update does not come through here, so anything writing
        the flag that way sets the date itself. The constraint is what
        makes that a failure rather than a quiet disagreement.
        """
        if self.is_archived and self.archived_at is None:
            self.archived_at = timezone.now()
        elif not self.is_archived:
            self.archived_at = None
        fields = kwargs.get("update_fields")
        if fields is not None and "is_archived" in fields:
            kwargs["update_fields"] = [*fields, "archived_at"]
        super().save(*args, **kwargs)

    def clean(self):
        """A component sits under one of its own service's components.

        Nothing in the column says whose component the parent is.
        Without this a service's tree reaches into another service's,
        and a page shows one product's components under another.
        """
        super().clean()
        if self.parent_id is None:
            return
        if self.parent_id == self.pk:
            raise ValidationError({"parent": "A component cannot be its own parent."})
        if self.parent.service_id != self.service_id:
            raise ValidationError(
                {"parent": "That component belongs to another service."}
            )

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
