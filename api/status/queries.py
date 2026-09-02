"""What a caller reads about a component's state, as SQL.

A severity is not a column. It is the open row of a status history. An
event's next move is the soonest end or start among the live ones. Both
are subqueries, and a list orders and filters on them.

These lived in `common.ordering`, which made the base layer import the
app it describes.
"""

from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce

from status.choices import EventKind
from status.models import ComponentStatus, ServiceEvent

# The open status row is the current one. So the severity a board sorts
# on is a subquery, not a column.
CURRENT_SEVERITY = Subquery(
    ComponentStatus.objects.filter(
        component=OuterRef("pk"), ended_at__isnull=True
    ).values("severity")[:1]
)

# What the Maintenance tab sorts on: when this component next changes state.
# A running window transitions when it ends; one that has not started
# transitions when it starts.
NEXT_TRANSITION = Coalesce(
    Subquery(
        ServiceEvent.objects.filter(
            affected_components=OuterRef("pk"),
            kind=EventKind.MAINTENANCE,
            ends_at__isnull=False,
        )
        .order_by("ends_at")
        .values("ends_at")[:1]
    ),
    Subquery(
        ServiceEvent.objects.filter(
            affected_components=OuterRef("pk"),
            kind=EventKind.MAINTENANCE,
        )
        .order_by("starts_at")
        .values("starts_at")[:1]
    ),
)
