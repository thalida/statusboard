"""What a caller may narrow a catalog list by.

Beside `dashboards.filters`, and apart from the views that use them. A
filter is the query contract, and it is read on its own more often than
the view around it.
"""

from django.db.models import Count, Q
from django_filters import rest_framework as filters

from catalog.models import Service, ServiceComponent
from status.models import ServiceEvent


class ServiceFilter(filters.FilterSet):
    # Declared: django-filter cannot generate a count comparison off a related set.
    tracked_component_count__gt = filters.NumberFilter(method="filter_tracked_gt")

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

    def filter_tracked_gt(self, queryset, name, value):
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        return queryset.annotate(
            n=Count(
                "components__tracked_by",
                filter=Q(components__tracked_by__dashboard__owner=user),
                distinct=True,
            )
        ).filter(n__gt=value)


class ComponentFilter(filters.FilterSet):
    # `status` is not a relation. A component has a history of statuses
    # and the open one is current. Same contract name, same annotation.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )

    class Meta:
        model = ServiceComponent
        fields = {"is_overall": ["exact"]}


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
