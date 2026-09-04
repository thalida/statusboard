from django.db.models import Count, Min


class AggregateSet:
    """Fills the `aggregates` key of a list response.

    Computed over the whole filtered collection, not the page. A screen
    shows "3 down, 12 operational" from the request that drew the rows,
    instead of a request per count.

    A view names its class in `aggregate_set` and the paginator builds it.
    Put every collection-wide value here, never at the top level.
    """

    def __init__(self, queryset):
        self.queryset = queryset

    def build(self):
        return {"total": self.queryset.count()}


class StatusAggregateSet(AggregateSet):
    """For any list of components. Discover, a service's parts, a board."""

    def build(self):
        data = super().build()
        data["by_severity"] = self._by_severity()
        data["next_refresh_at"] = self._next_refresh_at()
        data["oldest_refreshed_at"] = self._oldest_refreshed_at()
        return data

    def _by_severity(self):
        rows = (
            self.queryset.filter(statuses__ended_at__isnull=True)
            .values("statuses__severity")
            .annotate(n=Count("id", distinct=True))
        )
        return {str(r["statuses__severity"]): r["n"] for r in rows}

    def _next_refresh_at(self):
        return self.queryset.aggregate(v=Min("service__poller__next_at"))["v"]

    def _oldest_refreshed_at(self):
        return self.queryset.aggregate(v=Min("service__poller__last_success_at"))["v"]


class EventAggregateSet(AggregateSet):
    def build(self):
        data = super().build()
        rows = self.queryset.values("phase").annotate(n=Count("id"))
        data["by_phase"] = {r["phase"]: r["n"] for r in rows}
        return data
