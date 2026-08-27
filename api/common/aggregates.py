class AggregateSet:
    """Values computed over the whole collection, not the page.

    An endpoint subclasses this and adds its own.
    Put every collection-wide value here, never at the top level.
    """

    def __init__(self, queryset):
        self.queryset = queryset

    def build(self):
        return {"total": self.queryset.count()}
