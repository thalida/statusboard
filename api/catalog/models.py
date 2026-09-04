from urllib.parse import urlparse, urlunparse

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVectorField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from catalog.choices import StatusPageProvider
from common.models import BaseModel
from common.queries import related_count


class ServiceQuerySet(models.QuerySet):
    def for_display(self, user=None):
        """Everything `ServiceSerializer` reads, in four queries.

        The service page reads one service. Three of its fields are
        counted or nested. The nested one is a whole component, which
        asks seven more.
        """
        from django.contrib.auth.models import AnonymousUser

        tracked = models.Value(0, output_field=models.IntegerField())
        if user is not None and not isinstance(user, AnonymousUser):
            tracked = related_count(
                ServiceComponent.objects.filter(boards__owner=user), "service"
            )
        return (
            self.select_related("status_page", "poller")
            .annotate(
                _component_count=related_count(
                    ServiceComponent.objects.filter(
                        is_overall=False, is_archived=False
                    ),
                    "service",
                ),
                _tracked_component_count=tracked,
            )
            .prefetch_related(
                models.Prefetch(
                    "components",
                    queryset=ServiceComponent.objects.filter(
                        is_overall=True
                    ).for_display(user),
                    to_attr="_overall_components",
                )
            )
        )


class Service(BaseModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(
        unique=True,
        blank=True,
        help_text="Derived from the name when left blank.",
    )
    logo = models.URLField(blank=True, default="")
    homepage_url = models.URLField(blank=True, default="")
    objects = ServiceQuerySet.as_manager()

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

    def overall_component(self):
        """The rollup component, which is the service's own status.

        This and the two below read what `for_display` prepared. A row
        fetched without it asks instead. The underscore names are that
        queryset's, so a rename cannot leave a reader behind.
        """
        prepared = getattr(self, "_overall_components", None)
        if prepared is None:
            return self.components.filter(is_overall=True).first()
        return prepared[0] if prepared else None

    def component_count(self):
        """The parts. The rollup is excluded, because it is the service."""
        prepared = getattr(self, "_component_count", None)
        if prepared is not None:
            return prepared
        return self.components.filter(is_overall=False, is_archived=False).count()

    def tracked_component_count(self, user):
        """How many parts this user has on a board."""
        if user is None or not user.is_authenticated:
            return 0
        prepared = getattr(self, "_tracked_component_count", None)
        if prepared is not None:
            return prepared
        return (
            ServiceComponent.objects.filter(service=self, boards__owner=user)
            .distinct()
            .count()
        )

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

        # The one import this module makes into polling, and it is
        # deferred. `Poller` holds the column, so `polling.models`
        # imports this file. A service triggers the row, so either this
        # import waits until it is called, or polling listens for a
        # save. This is the smaller of the two.
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


class ServiceRequest(BaseModel):
    """A status page somebody asked for and we could not read.

    One row per URL, not one per request. A row per request would
    answer one question twice once a URL was triaged.

    There is no `requested_by`. `BaseModel.created_by` already holds
    it, null when the asker was signed out. The v1 spec deleted
    `Service.added_by` for the same reason.

    There is no state column either. Nothing closes a request yet, so
    it would have no writer.
    """

    url = models.URLField(unique=True)
    # The demand signal. Nothing else records how often a URL was
    # asked for. This is that record, not a copy of one.
    request_count = models.PositiveIntegerField(default=1)
    last_requested_at = models.DateTimeField(default=timezone.now)

    class Meta(BaseModel.Meta):
        ordering = ["-request_count", "-last_requested_at"]

    def __str__(self):
        return self.url


def _descendant_count():
    """How many components sit under each row, in one query for the page.

    `related_count` cannot express this. It compares a column to the
    outer key. `ancestor_ids` holds an array, so the outer key goes in
    as a one element array of its own.

    The constant in `values` is what makes this one aggregate. Without
    it Django counts per row and returns one row a component, which a
    subquery in a SELECT list refuses.
    """
    key = models.Func(
        models.OuterRef("pk"),
        template="ARRAY[%(expressions)s]",
        output_field=ArrayField(models.UUIDField()),
    )
    counted = (
        ServiceComponent.objects.filter(ancestor_ids__contains=key)
        .order_by()
        .values(one_group=models.Value(1))
        .annotate(total=models.Count("pk"))
        .values("total")
    )
    return Coalesce(models.Subquery(counted, output_field=models.IntegerField()), 0)


class ServiceComponentQuerySet(models.QuerySet):
    def search(self, q):
        """Rank a query against the stored path.

        Websearch mode, so several words are an AND. A caller ordering
        by anything else drops the rank and keeps the filter.
        """
        query = SearchQuery(q, search_type="websearch")
        return (
            self.filter(search_document=query)
            .annotate(rank=SearchRank(models.F("search_document"), query))
            .order_by("-rank")
        )

    def for_display(self, user=None):
        """Everything `ComponentSerializer` reads, in four queries.

        It answered seven fields with a query each, per row. A page of
        fifty cost three hundred and fifty six.

        A row that skipped this still serializes, because a single
        service nests one. So the fast path has to be asked for.
        """
        from django.contrib.auth.models import AnonymousUser

        from status.models import ComponentStatus, ServiceEvent

        tracked = models.Value(None, output_field=models.BooleanField())
        if user is not None and not isinstance(user, AnonymousUser):
            # Through DashboardItem, which names the column `component`.
            # The through model is explicit, so it is not the automatic
            # `servicecomponent`.
            tracked = models.Exists(
                self.model.boards.through.objects.filter(
                    component=models.OuterRef("pk"), dashboard__owner=user
                )
            )
        return (
            self.select_related("service", "parent", "parent__parent")
            .annotate(
                _descendant_count=_descendant_count(),
                _is_tracked=tracked,
            )
            .prefetch_related(
                models.Prefetch(
                    "statuses",
                    # The status carries when its service was last read,
                    # which is on the poller, one join further out.
                    queryset=ComponentStatus.objects.filter(
                        ended_at__isnull=True
                    ).select_related("component__service__poller"),
                    to_attr="_open_statuses",
                ),
                models.Prefetch(
                    "events",
                    queryset=ServiceEvent.objects.live(),
                    to_attr="_live_events",
                ),
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
    # The chain above this one, root first, written by reconcile. A
    # component's Components tab lists every descendant, and a self-FK
    # lookup returns one level. Walking the chain per row cannot use an
    # index either.
    ancestor_ids = ArrayField(
        models.UUIDField(), default=list, blank=True, editable=False
    )
    # The whole path, weighted, written by reconcile. Searching a
    # service's name must also reach its components. Walking `parent`
    # at query time cannot use an index.
    search_document = SearchVectorField(null=True, editable=False)
    objects = ServiceComponentQuerySet.as_manager()

    status_page_order = models.IntegerField(verbose_name="Page order", default=0)
    is_overall = models.BooleanField(verbose_name="Overall", default=False)
    # Ticked on the overall component to feature a whole service. It is
    # the first key of the suggested sort. On day one that is the whole
    # sort: every watcher count starts at zero.
    is_featured = models.BooleanField(verbose_name="Featured", default=False)
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
        indexes = [
            GinIndex(fields=["ancestor_ids"], name="components_by_ancestor"),
            GinIndex(fields=["search_document"], name="components_by_search"),
        ]

    def live_events(self, kind):
        """The live events of one kind.

        This and the three below read what `for_display` prepared. A row
        fetched without it asks instead.
        """
        prepared = getattr(self, "_live_events", None)
        if prepared is None:
            return list(self.events.live(kind))
        return [event for event in prepared if event.kind == kind]

    def open_status(self):
        """The status span still running, if there is one."""
        prepared = getattr(self, "_open_statuses", None)
        if prepared is None:
            return self.statuses.filter(ended_at__isnull=True).first()
        return prepared[0] if prepared else None

    def descendant_count(self):
        """How many components sit anywhere under this one."""
        if self.is_overall:
            return 0
        prepared = getattr(self, "_descendant_count", None)
        if prepared is None:
            return ServiceComponent.objects.filter(
                ancestor_ids__contains=[self.pk]
            ).count()
        return prepared

    def is_tracked_by(self, user):
        """Whether this user has it on a board. Null if nobody asked."""
        if user is None or not user.is_authenticated:
            return None
        prepared = getattr(self, "_is_tracked", None)
        if prepared is None:
            return self.boards.filter(owner=user).exists()
        return prepared

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
