from django_filters import rest_framework as filters
from rest_framework.filters import BaseFilterBackend

FIELDS_DESCRIPTION = (
    "Comma-separated fields to return. A dotted path prunes inside a "
    "nested object rather than dropping it."
)


class FieldsBackend(BaseFilterBackend):
    """Declare `?fields=` for drf-spectacular.

    `FieldsMixin` does the pruning. This adds the parameter to every
    list operation. `common.schema.FieldsAutoSchema` adds it to detail
    operations. drf-spectacular never asks a backend about those.
    """

    def filter_queryset(self, request, queryset, view):
        return queryset

    def get_schema_operation_parameters(self, view):
        return [
            {
                "name": "fields",
                "required": False,
                "in": "query",
                "description": FIELDS_DESCRIPTION,
                "schema": {"type": "string"},
            }
        ]


class SeverityFilterMixin(filters.FilterSet):
    """How a caller narrows a list of components by severity.

    Declared, not generated. A component has a history of statuses and
    the open one is current. So there is no `status` relation to
    generate from. The contract's name points at the `severity_now`
    annotation each view supplies instead.

    A `FilterSet` rather than a plain mixin. django-filter collects
    declared filters only from a base that already carries them. It
    names no model, so `common` still imports no app. A subclass brings
    its own `Meta`.
    """

    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )
    # The Severity filter offers all six values at once. One exact match
    # cannot serve it.
    status__severity__in = filters.BaseInFilter(
        field_name="severity_now", lookup_expr="in"
    )
