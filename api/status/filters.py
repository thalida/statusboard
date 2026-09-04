"""What a caller may narrow the event feed by.

Beside the views, and apart from them. A filter is the query contract,
and it is read on its own more often than the view around it.
"""

from django_filters import rest_framework as filters

from status.choices import CLOSED_PHASES, EventPhaseState
from status.models import ServiceEvent


class EventFilter(filters.FilterSet):
    # Declared, not generated. `CLOSED_PHASES` draws the line between
    # an open phase and a closed one. A client restating it is a
    # second copy of one rule.
    phase = filters.ChoiceFilter(choices=EventPhaseState.choices, method="filter_phase")
    service = filters.CharFilter(field_name="service__slug")
    component = filters.UUIDFilter(field_name="affected_components__id")
    dashboard = filters.UUIDFilter(method="filter_dashboard")

    class Meta:
        model = ServiceEvent
        fields = {"kind": ["exact"]}

    def filter_phase(self, queryset, name, value):
        if value == EventPhaseState.CLOSED:
            return queryset.filter(phase__in=CLOSED_PHASES)
        return queryset.exclude(phase__in=CLOSED_PHASES)

    def filter_dashboard(self, queryset, name, value):
        """Everything posted across the services on one board.

        The board's rows are components, and an event names components.
        A user reaches only their own board: the view checks the owner
        before this runs.
        """
        return queryset.filter(
            affected_components__tracked_by__dashboard_id=value
        ).distinct()
