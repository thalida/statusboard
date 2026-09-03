"""What a caller reads about a service, as SQL.

A service's own severity is its overall component's. Who watches it is
counted through the boards its components sit on. Both are questions
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

# Who tracks a service, counted when it is read. It was a column that a
# signal kept true, and four write paths never reached the signal.
#
# Two readers, two shapes. Only the suggestion order needs the number, so
# only it pays for a distinct count over three joins.
WATCHER_COUNT = Count("components__boards__owner", distinct=True)


def is_tracked(field="pk"):
    """Whether anybody tracks any part of a service.

    `Exists` stops at the first row. The poller asks this every beat and
    never needs to know how many.
    """
    from dashboards.models import DashboardItem

    return Exists(DashboardItem.objects.filter(component__service=OuterRef(field)))
