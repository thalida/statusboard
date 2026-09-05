"""Ordering that knows about no model.

The domain subqueries this used to hold moved to `status.queries` and
`catalog.queries`. `common` is the layer everything imports, and it was
importing `catalog` and `status` back.
"""

from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter


class MappedOrderingFilter(OrderingFilter):
    """Translate a public ordering value to a flat field.

    A cursor cannot order on a related path or on a name that is not a field.
    A view declares `ordering_map` and annotates the flat field it names.

    A value the view does not declare answers 400, the way `?fields=`
    refuses an unknown name. Dropping it left the caller reading a list
    sorted by something else, with nothing to say so.
    """

    def remove_invalid_fields(self, queryset, fields, view, request):
        mapping = getattr(view, "ordering_map", {})
        allowed = set(getattr(view, "ordering_fields", ())) | set(mapping)
        out = []
        for term in fields:
            name = term.removeprefix("-")
            if name not in allowed:
                raise ValidationError({"ordering": [f"Unknown ordering: {term}."]})
            mapped = mapping.get(name, [name])
            if not term.startswith("-"):
                out.extend(mapped)
            elif len(mapped) == 1 and not mapped[0].startswith("-"):
                out.append(f"-{mapped[0]}")
            else:
                # An editorial order already names its own directions.
                # A second prefix built `--is_featured`, which reached
                # the ORM as a 500.
                raise ValidationError({"ordering": [f"Cannot reverse: {term}."]})
        return out
