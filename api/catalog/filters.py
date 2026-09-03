"""What a caller may narrow a catalog list by.

Beside `dashboards.filters`, and apart from the views that use them. A
filter is the query contract, and it is read on its own more often than
the view around it.
"""

from django_filters import rest_framework as filters

from catalog.models import Service, ServiceComponent
from status.models import ServiceEvent


class ServiceFilter(filters.FilterSet):
    # Declared for a second reason. `overall_component` is not a relation
    # on Service. The current severity is not a column either. It is the
    # open row of a component's status history. So the contract's name is
    # kept, pointed at the view's `severity_now` annotation.
    overall_component__status__severity = filters.NumberFilter(
        field_name="severity_now"
    )
    overall_component__status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )

    class Meta:
        model = Service
        fields = {
            "status_page__provider": ["exact"],
            "is_featured": ["exact"],
        }


class ComponentFilter(filters.FilterSet):
    # `status` is not a relation. A component has a history of statuses
    # and the open one is current. Same contract name, same annotation.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )
    # The Severity filter offers all six values at once. One exact match
    # cannot serve it.
    status__severity__in = filters.BaseInFilter(
        field_name="severity_now", lookup_expr="in"
    )
    service = filters.CharFilter(field_name="service__slug")
    # Every descendant, not one level. `parent` would name a query this
    # does not run.
    ancestor = filters.UUIDFilter(method="filter_ancestor")
    event = filters.UUIDFilter(field_name="events__id")
    # `for_display` annotates this per viewer. It is not a column, so
    # there is nothing to generate the filter from.
    is_tracked = filters.BooleanFilter(method="filter_is_tracked")

    class Meta:
        model = ServiceComponent
        fields = {"is_overall": ["exact"]}

    def filter_ancestor(self, queryset, name, value):
        """Match the stored chain, which the GIN index answers.

        `ancestor_ids` holds every step above a row. A containment test
        on it reaches any depth in one comparison.
        """
        return queryset.filter(ancestor_ids__contains=[value])

    def filter_is_tracked(self, queryset, name, value):
        """Answer it here, because nobody signed out tracks anything.

        Both directions are true for that reader, so neither is an
        error. `for_display` annotates `_is_tracked` as NULL then, and
        SQL reads `NOT NULL` as NULL rather than true. Comparing against
        the annotation would drop every row from Untracked.
        """
        if self.request is None or self.request.user.is_anonymous:
            return queryset.none() if value else queryset
        return queryset.filter(_is_tracked=value)


class ServiceEventFilter(filters.FilterSet):
    class Meta:
        model = ServiceEvent
        fields = {
            "kind": ["exact"],
            "phase": ["exact", "in"],
            "ends_at": ["isnull", "gte"],
            "starts_at": ["gte", "lte"],
            "affected_components": ["exact"],
        }
