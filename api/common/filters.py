from rest_framework.filters import BaseFilterBackend


class FieldsBackend(BaseFilterBackend):
    """Declare `?fields=` for drf-spectacular.

    `FieldsMixin` does the pruning. This adds the parameter to every operation.
    """

    def filter_queryset(self, request, queryset, view):
        return queryset

    def get_schema_operation_parameters(self, view):
        return [
            {
                "name": "fields",
                "required": False,
                "in": "query",
                "description": (
                    "Comma-separated fields to return. A dotted path prunes inside a "
                    "nested object rather than dropping it."
                ),
                "schema": {"type": "string"},
            }
        ]
