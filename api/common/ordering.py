"""Ordering that knows about no model.

The domain subqueries this used to hold moved to `status.queries` and
`catalog.queries`. `common` is the layer everything imports, and it was
importing `catalog` and `status` back.
"""

from rest_framework.filters import OrderingFilter


class MappedOrderingFilter(OrderingFilter):
    """Translate a public ordering value to a flat field.

    A cursor cannot order on a related path or on a name that is not a field.
    A view declares `ordering_map` and annotates the flat field it names.
    """

    def remove_invalid_fields(self, queryset, fields, view, request):
        mapping = getattr(view, "ordering_map", {})
        allowed = set(getattr(view, "ordering_fields", ())) | set(mapping)
        out = []
        for term in fields:
            name = term.lstrip("-")
            if name not in allowed:
                continue
            for mapped in mapping.get(name, [name]):
                out.append(f"-{mapped}" if term.startswith("-") else mapped)
        return out
