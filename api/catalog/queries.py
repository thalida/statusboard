"""What a caller reads about a service, as SQL.

A service's own severity is its overall component's. Who watches a
component is counted through the boards it sits on. Both are questions
about the catalog, so they live here.

These lived in `common.ordering`, which made the base layer import the
app it describes.
"""

from django.db.models import Count, Exists, OuterRef, Subquery

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
