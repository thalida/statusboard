from django.db.models import Exists, OuterRef
from django_filters import rest_framework as filters

from catalog.models import ServiceComponent
from status.choices import CLOSED_PHASES, EventKind
from status.models import ServiceEvent


class BoardComponentFilter(filters.FilterSet):
    """`event` is declared, not generated.

    `ServiceEvent` and `ServiceComponent` are many-to-many.
    django-filter applies each parameter as its own `.filter()` call.
    On a many-to-many, each call joins again and can match a different event.
    Both conditions must sit in one call, so this is a single subquery.
    """

    event = filters.ChoiceFilter(choices=EventKind.choices, method="filter_event")

    # Declared for the same reason as the catalog's. A component has a
    # history of `statuses`. The open one is current. So there is no
    # `status` relation to generate from. The contract's name points at
    # the annotation instead.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )

    class Meta:
        model = ServiceComponent
        fields = []

    def filter_event(self, queryset, name, value):
        live = ServiceEvent.objects.filter(
            kind=value, affected_components=OuterRef("pk")
        ).exclude(phase__in=CLOSED_PHASES)
        return queryset.filter(Exists(live))
