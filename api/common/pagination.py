from django.conf import settings
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from common.aggregates import AggregateSet


class EnvelopePagination(CursorPagination):
    page_size = settings.DEFAULT_PAGE_SIZE
    max_page_size = settings.MAX_PAGE_SIZE
    page_size_query_param = "page_size"
    ordering = "-created_at"
    tiebreak = "-created_at"

    def paginate_queryset(self, queryset, request, view=None):
        aggregate_class = getattr(view, "aggregate_set", AggregateSet)
        self._aggregates = aggregate_class(queryset).build()
        return super().paginate_queryset(queryset, request, view)

    def get_ordering(self, request, queryset, view):
        # A cursor needs a unique key. Non-unique ordering repeats or skips rows.
        ordering = super().get_ordering(request, queryset, view)
        if self.tiebreak in ordering or "created_at" in ordering:
            return ordering
        return (*ordering, self.tiebreak)

    def get_paginated_response(self, data):
        return Response(
            {
                "aggregates": self._aggregates,
                "next": self.get_next_link(),
                "results": data,
            }
        )
