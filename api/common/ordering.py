from django.db.models import Count, Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce
from rest_framework.filters import OrderingFilter

from status.choices import EventKind
from status.models import ComponentStatus, ServiceEvent


class MappedOrderingFilter(OrderingFilter):
    """Translate a public ordering value to a flat field.

    A cursor cannot order on a related path or on a name that is not a field.
    A view declares `ordering_map` and annotates the flat field it names.
    """

    def remove_invalid_fields(self, queryset, fields, view, request):
        mapping = getattr(view, "ordering_map", {})
        allowed = set(getattr(view, "ordering_fields", ())) | set(mapping)
        out = []
        for term in fields:
            name = term.lstrip("-")
            if name not in allowed:
                continue
            for mapped in mapping.get(name, [name]):
                out.append(f"-{mapped}" if term.startswith("-") else mapped)
        return out


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
WATCHER_COUNT = Count("components__tracked_by__dashboard__owner", distinct=True)


def is_tracked(field="pk"):
    """Whether anybody tracks any part of a service.

    `Exists` stops at the first row. The poller asks this every beat and
    never needs to know how many.
    """
    from dashboards.models import DashboardItem

    return Exists(DashboardItem.objects.filter(component__service=OuterRef(field)))
