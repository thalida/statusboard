"""What a caller reads about the catalog, as SQL.

Most are a bare expression, handed to `annotate()`. Chainable
vocabulary is a queryset method, and lives on the queryset instead.

The walk down `parent` is here too. It is raw SQL because a recursive
CTE has no ORM form, and it answers a catalog read.

These lived in `common.ordering`, which made the base layer import the
app it describes.
"""

from django.db import connection
from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery
from django.db.models.expressions import RawSQL

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


# Everything under one component, walked down `parent`. `?ancestor=`
# and every descendant count ask this one question, so they read one
# definition of it.
#
# `walked` carries the ids already visited, and the step drops a row
# that is in it. `parent` points at this same table and nothing forbids
# a loop, so an unguarded walk never ends. A depth ceiling would end it
# too, but it would also cut a deep tree that is not a loop.
#
# The step tests `service_id` as well. A component's tree stops at its
# own service, which is the rule `ServiceComponent.ancestors` follows
# climbing the other way.
#
# `steps` is 0 on the component itself. No reader counts a component
# among the ones below it.
_BELOW = """
WITH RECURSIVE below AS (
        SELECT seed.id, seed.is_archived, seed.service_id,
               ARRAY[seed.id] AS walked, 0 AS steps
        FROM {table} seed
        WHERE seed.id = {root}
    UNION ALL
        SELECT step.id, step.is_archived, step.service_id,
               below.walked || step.id, below.steps + 1
        FROM {table} step
        JOIN below ON step.parent_id = below.id
                  AND step.service_id = below.service_id
        WHERE NOT step.id = ANY(below.walked)
)
"""


def _table():
    """The component table, quoted. Read late, so no import runs early."""
    from catalog.models import ServiceComponent

    return connection.ops.quote_name(ServiceComponent._meta.db_table)


def _below(root, tail):
    """The walk, rooted where the caller says, ending as it asks."""
    return _BELOW.format(table=_table(), root=root) + tail


class _CountsOwnRow(RawSQL):
    """Raw SQL that reads the row it is annotated on.

    Django groups a page by every column it selects, and it cannot see
    inside raw SQL. Left alone it groups by the whole subquery, which
    Postgres refuses. The row's key is already grouped, and this counts
    from that key alone.
    """

    def get_group_by_cols(self):
        return []


def descendant_ids(component_id):
    """Every component under one, at any depth, as a subquery.

    `?ancestor=` reads this. An archived row is walked through and not
    dropped, because the caller narrows the result to what it serves.
    """
    return RawSQL(_below("%s", "SELECT id FROM below WHERE steps > 0"), [component_id])


def descendant_count():
    """How many components sit under each row, in one query for the page.

    Archived rows are left out of the total. A caller is not served one
    anywhere else, so a count that held them would name components no
    list returns. The walk still passes through them, or an archived
    group would hide the live rows under it.
    """
    # The row being annotated, named by the table itself. Django never
    # aliases the base table of a query, and the walk aliases its own.
    sql = _below(
        f"{_table()}.{connection.ops.quote_name('id')}",
        "SELECT count(*) FROM below WHERE steps > 0 AND NOT is_archived",
    )
    return _CountsOwnRow(f"({sql})", [], output_field=IntegerField())
