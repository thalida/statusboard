from urllib.parse import urlparse, urlunparse

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

from catalog.choices import ServiceSource, StatusPageProvider
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

        from catalog.queries import component_count

        tracked = models.Value(0, output_field=models.IntegerField())
        if user is not None and not isinstance(user, AnonymousUser):
            tracked = related_count(
                ServiceComponent.objects.visible().filter(boards__owner=user),
                "service",
            )
        return (
            self.select_related("status_page", "poller")
            .annotate(
                component_count=component_count(),
                tracked_component_count=tracked,
            )
            .prefetch_related(
                models.Prefetch(
                    "components",
                    queryset=ServiceComponent.objects.filter(
                        is_overall=True
                    ).for_display(user),
                    to_attr="overall_components",
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
    # How the row arrived. `created_by` says who, and this says how.
    # Admin only: no screen reads it, so no serializer carries it.
    source = models.CharField(
        max_length=32,
        choices=ServiceSource.choices,
        default=ServiceSource.MANUAL,
        db_default=ServiceSource.MANUAL,
    )
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

        `for_display` prefetches it. A row fetched without that asks
        instead, because a single service nests one.

        The name is singular against the plural prefetch, so the two
        never collide.
        """
        prepared = getattr(self, "overall_components", None)
        if prepared is None:
            return self.components.filter(is_overall=True).first()
        return prepared[0] if prepared else None

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

        # A person caused the service, so the poller they spawned
        # carries them. The system account signs it only when the
        # service has none. A blank author reads as one that was lost.
        author = self.created_by or get_user_model().objects.system()
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


class ServiceComponentQuerySet(models.QuerySet):
    def visible(self):
        """The components a caller is served, anywhere.

        The provider stopped publishing an archived one. Every list,
        every count, the detail and the track write read this. So no two
        of them can answer the same question differently.

        It is not part of `for_display`. That queryset also prefetches a
        service's rollup, and a service whose rollup is archived still
        needs a header status.
        """
        return self.filter(is_archived=False)

    def search(self, q):
        """Narrow to what every typed word describes.

        A word matches the component's own name or its service's, so
        `twilio` reaches Twilio's SMS row. Several words are an AND, so
        `twilio sms` reaches that row and not its siblings.

        The result is unordered. The list view decides what leads a
        search. An ordering backend runs after this and would discard
        any order set here.
        """
        rows = self
        for term in q.split():
            rows = rows.filter(
                models.Q(name__icontains=term) | models.Q(service__name__icontains=term)
            )
        return rows

    def for_display(self, user=None):
        """Everything `ComponentSerializer` reads, in four queries.

        It answered seven fields with a query each, per row. A page of
        fifty cost three hundred and fifty six.

        Every path that serializes a component calls this. A path that
        forgets raises `AttributeError` on the first count, rather than
        running one query a row in silence.
        """
        from django.contrib.auth.models import AnonymousUser

        from catalog.queries import descendant_count
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
                descendant_count=descendant_count(),
                is_tracked=tracked,
            )
            .prefetch_related(
                models.Prefetch(
                    "statuses",
                    # The status carries when its service was last read,
                    # which is on the poller, one join further out.
                    queryset=ComponentStatus.objects.filter(
                        ended_at__isnull=True
                    ).select_related("component__service__poller"),
                    to_attr="open_statuses",
                ),
                models.Prefetch(
                    "events",
                    queryset=ServiceEvent.objects.live(),
                    # The one name that keeps its underscore. Its reader
                    # is `live_events`, so the plain name would shadow
                    # the method that reads it.
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
    objects = ServiceComponentQuerySet.as_manager()

    status_page_order = models.IntegerField(verbose_name="Page order", default=0)
    is_overall = models.BooleanField(verbose_name="Overall", default=False)
    # Ticked on any component. The suggested sort leads with it. A
    # featured rollup surfaces its service, and a featured leaf
    # surfaces that part. Severity is the next key, so it breaks the
    # tie among the featured rows.
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

    # The rollup is never a parent, but `is_overall` belongs to the
    # parent row, not this one. A `CheckConstraint` sees one row, so it
    # cannot read a joined column and cannot express this. Migration
    # 0010 adds a trigger instead, named `rollup_is_not_a_parent`. It
    # checks both directions: a row parented under the rollup, and a
    # row with children gaining the flag.
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

    def live_events(self, kind):
        """The live events of one kind.

        This and the two below read what `for_display` prepared. Each
        picks one row, or one kind, out of a prefetch. So the method
        and the attribute cannot share a name.
        """
        prepared = getattr(self, "_live_events", None)
        if prepared is None:
            return list(self.events.live(kind))
        return [event for event in prepared if event.kind == kind]

    def open_status(self):
        """The status span still running, if there is one."""
        prepared = getattr(self, "open_statuses", None)
        if prepared is None:
            return self.statuses.filter(ended_at__isnull=True).first()
        return prepared[0] if prepared else None

    def is_tracked_by(self, user):
        """Whether this user has it on a board. Null if nobody asked."""
        if user is None or not user.is_authenticated:
            return None
        prepared = getattr(self, "is_tracked", None)
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

        Nothing in the column says whose component the parent is, or
        that the parent is not the rollup. Without the first check a
        service's tree reaches into another service's. Without the
        second a rollup gains children, and every descendant count and
        breadcrumb under it reads wrong.
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
        if self.parent.is_overall:
            raise ValidationError(
                {"parent": "The overall component is never a parent."}
            )

    @property
    def ancestors(self):
        """The components above this one, top down.

        A provider can nest a component under another. The chain is what
        tells you where it sits on the status page.

        Two rules end the walk. A loop is possible, because the column
        points at its own table. And the chain stops at the service.
        Moving a component leaves its old children pointing across. A
        step there names a row this service's lists never hold.

        `catalog.queries` walks the other direction under the same two
        rules. The rows here are already loaded, so this stays Python.
        """
        chain, node, seen = [], self.parent, {self.pk}
        while (
            node is not None
            and node.pk not in seen
            and node.service_id == self.service_id
        ):
            seen.add(node.pk)
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    @property
    def visible_ancestors(self):
        """The ancestors a caller is served, top down.

        `ServiceComponentQuerySet.visible` is the same rule in SQL.
        `ancestors` has already loaded these rows, so asking the
        database again would cost a query a row.

        A dropped step makes the chain shorter, never broken. Every
        other reader answers "not served" by leaving the row out. A
        marker node would carry an id nothing can fetch.
        """
        return [row for row in self.ancestors if not row.is_archived]

    @property
    def path(self):
        """Where the component sits, read from the service down."""
        names = [self.service.name, *(a.name for a in self.ancestors), self.name]
        return " / ".join(names)

    def __str__(self):
        return self.path
