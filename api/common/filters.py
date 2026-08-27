from rest_framework.filters import BaseFilterBackend

FIELDS_DESCRIPTION = (
    "Comma-separated fields to return. A dotted path prunes inside a "
    "nested object rather than dropping it."
)


class FieldsBackend(BaseFilterBackend):
    """Declare `?fields=` for drf-spectacular.

    `FieldsMixin` does the pruning. This adds the parameter to every
    list operation; `common.schema.FieldsAutoSchema` adds it to detail
    operations, which drf-spectacular never asks a backend about.
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
