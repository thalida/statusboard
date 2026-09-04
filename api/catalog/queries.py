"""What a caller reads about the catalog, as SQL.

Each one is a bare expression, handed to `annotate()`. Chainable
vocabulary is a queryset method, and lives on the queryset instead.

These lived in `common.ordering`, which made the base layer import the
app it describes.
"""

from django.db.models import Count, Exists, OuterRef, Subquery

from common.queries import related_count
from status.models import ComponentStatus

# A service's own status is the open row of its overall component. That
# is the provider's page-level reading, not the worst of its parts.
OVERALL_SEVERITY = Subquery(
    ComponentStatus.objects.filter(
        component__service=OuterRef("pk"),
        component__is_overall=True,
        ended_at__isnull=True,
    ).values("severity")[:1]
)

# Who tracks one component, counted when it is read. It was a column
# that a signal kept true, and four write paths never reached the
# signal. `DashboardItem` points straight at a component, so this is one
# join.
COMPONENT_WATCHER_COUNT = Count("boards__owner", distinct=True)


def is_tracked(field="pk"):
    """Whether anybody tracks any part of a service.

    `Exists` stops at the first row. The poller asks this every beat and
    never needs to know how many.
    """
    from dashboards.models import DashboardItem

    return Exists(DashboardItem.objects.filter(component__service=OuterRef(field)))


def component_count():
    """How many components a service publishes, in one query for the page.

    The rollup is the service itself, and an archived row is served
    nowhere. So neither is counted, and the number matches the
    provider's own page. The API field and the admin column read this,
    because two answers to one question drift apart.
    """
    from catalog.models import ServiceComponent

    return related_count(
        ServiceComponent.objects.visible().filter(is_overall=False), "service"
    )


def descendant_count():
    """How many components sit under each row, in one query for the page.

    Archived rows are left out. A caller is not served one anywhere
    else, so a count that included them would name components no list
    returns.
    """
    from catalog.models import ComponentAncestor

    return related_count(ComponentAncestor.objects.to_visible(), "ancestor")
