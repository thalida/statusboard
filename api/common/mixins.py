class FieldsMixin:
    """Prune serializer fields from `?fields=`.

    A dotted path prunes inside a nested serializer. It does not drop it.
    Set `fields_param = None` to always return the full shape.
    """

    fields_param = "fields"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.fields_param is None:
            return
        request = self.context.get("request")
        raw = (
            getattr(request, "query_params", {}).get(self.fields_param)
            if request
            else None
        )
        if not raw:
            return
        self._prune(self._parse(raw))

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
                child._prune(child._parse(",".join(children)))
