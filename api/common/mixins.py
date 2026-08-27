_UNSET = object()


class FieldsMixin:
    """Prune serializer fields from `?fields=`.

    A dotted path prunes inside a nested serializer. It does not drop it.
    Set `fields_param = None` to always return the full shape.

    A serializer built by hand inside a `SerializerMethodField` must be
    handed its own branch. Use `fields_tree=parent.child_tree(name)`.
    Left to read the request itself, it prunes by the parent's names.
    Then `?fields=id,overall_component.status` leaves the nested object
    holding `id` rather than `status`.
    """

    fields_param = "fields"

    def __init__(self, *args, **kwargs):
        tree = kwargs.pop("fields_tree", _UNSET)
        super().__init__(*args, **kwargs)
        if tree is _UNSET:
            tree = self._tree_from_request()
        self._fields_tree = tree
        if tree:
            self._prune(tree)

    def _tree_from_request(self):
        if self.fields_param is None:
            return None
        request = self.context.get("request")
        raw = (
            getattr(request, "query_params", {}).get(self.fields_param)
            if request
            else None
        )
        return self._parse(raw) if raw else None

    def child_tree(self, name):
        """The branch under `name`, for a serializer built in a method field."""
        branch = (getattr(self, "_fields_tree", None) or {}).get(name)
        return self._parse(",".join(branch)) if branch else None

    @staticmethod
    def _parse(raw):
        tree = {}
        for path in (p.strip() for p in raw.split(",") if p.strip()):
            head, _, tail = path.partition(".")
            branch = tree.setdefault(head, set())
            if tail:
                branch.add(tail)
        return tree

    def _prune(self, tree):
        for name in set(self.fields) - set(tree):
            self.fields.pop(name)
        for name, children in tree.items():
            child = self.fields.get(name)
            if children and hasattr(child, "_prune"):
                sub = child._parse(",".join(children))
                child._fields_tree = sub
                child._prune(sub)
