from django.db.models import Count, Min

from status.choices import CLOSED_PHASES, EventKind


class AggregateSet:
    """Values computed over the whole collection, not the page.

    An endpoint subclasses this and adds its own.
    Put every collection-wide value here, never at the top level.
    """

    def __init__(self, queryset):
        self.queryset = queryset

    def build(self):
        return {"total": self.queryset.count()}


class StatusAggregateSet(AggregateSet):
    """For any list of things carrying a status — services, components, a board."""

    def build(self):
        data = super().build()
        data["by_severity"] = self._by_severity()
        data["by_event_kind"] = self._by_event_kind()
        data["next_refresh_at"] = self._next_refresh_at()
        data["oldest_refreshed_at"] = self._oldest_refreshed_at()
        return data

    def _component_queryset(self):
        """Override where the rows are not components themselves."""
        return self.queryset

    def _by_severity(self):
        rows = (
            self._component_queryset()
            .filter(statuses__ended_at__isnull=True)
            .values("statuses__severity")
            .annotate(n=Count("id", distinct=True))
        )
        return {str(r["statuses__severity"]): r["n"] for r in rows}

    def _by_event_kind(self):
        counts = {}
        for kind in EventKind:
            counts[str(kind)] = (
                self._component_queryset()
                .filter(events__kind=kind)
                .exclude(events__phase__in=CLOSED_PHASES)
                .distinct()
                .count()
            )
        return counts

    def _next_refresh_at(self):
        return self._component_queryset().aggregate(v=Min("service__poller__next_at"))[
            "v"
        ]

    def _oldest_refreshed_at(self):
        return self._component_queryset().aggregate(
            v=Min("service__poller__last_success_at")
        )["v"]


class EventAggregateSet(AggregateSet):
    def build(self):
        data = super().build()
        rows = self.queryset.values("phase").annotate(n=Count("id"))
        data["by_phase"] = {r["phase"]: r["n"] for r in rows}
        return data
