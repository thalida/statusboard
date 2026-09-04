"""What a caller may narrow a catalog list by.

Beside `dashboards.filters`, and apart from the views that use them. A
filter is the query contract, and it is read on its own more often than
the view around it.
"""

from django_filters import rest_framework as filters

from catalog.models import ServiceComponent
from common.filters import SeverityFilterMixin


class ComponentFilter(SeverityFilterMixin):
    service = filters.CharFilter(field_name="service__slug")
    # Every descendant, not one level. `parent` would name a query this
    # does not run.
    ancestor = filters.UUIDFilter(field_name="ancestor_links__ancestor")
    event = filters.UUIDFilter(field_name="events__id")
    # `for_display` annotates this per viewer. It is not a column, so
    # there is nothing to generate the filter from.
    is_tracked = filters.BooleanFilter(method="filter_is_tracked")

    class Meta:
        model = ServiceComponent
        fields = {"is_overall": ["exact"]}

    def filter_is_tracked(self, queryset, name, value):
        """Answer it here, because nobody signed out tracks anything.

        Both directions are true for that reader, so neither is an
        error. `for_display` annotates `is_tracked` as NULL then, and
        SQL reads `NOT NULL` as NULL rather than true. Comparing against
        the annotation would drop every row from Untracked.
        """
        if self.request is None or self.request.user.is_anonymous:
            return queryset.none() if value else queryset
        return queryset.filter(is_tracked=value)
