"""Every read of an event, in one place.

Home, a service and a component show the same feed at different scopes.
The screens call it Updates. This names the model, and `/meta/`
publishes the labels.
"""

import uuid

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny

from common.aggregates import EventAggregateSet
from common.filters import FieldsBackend
from common.ordering import MappedOrderingFilter
from dashboards.models import Dashboard
from status.filters import EventFilter
from status.models import ServiceEvent
from status.serializers import ServiceEventSerializer


class EventListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceEventSerializer
    aggregate_set = EventAggregateSet
    filterset_class = EventFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    ordering_fields = ["starts_at", "ends_at"]
    ordering_map = {}
    ordering = ["-starts_at"]
    # get_queryset reads request.query_params, which schema generation
    # has not set. This names the model without running it.
    queryset = ServiceEvent.objects.none()

    def get_queryset(self):
        queryset = ServiceEvent.objects.select_related("service").prefetch_related(
            "updates"
        )
        board = self.request.query_params.get("dashboard")
        if not board:
            return queryset
        try:
            uuid.UUID(board)
        except ValueError:
            # Not a UUID. `EventFilter`'s own `dashboard` field rejects
            # it next, in the shape any other malformed filter value
            # gets. This method only owns whether the board is yours.
            return queryset
        # An anonymous caller cannot own a board. Refuse before
        # comparing against AnonymousUser, which get_object_or_404
        # cannot do.
        if not self.request.user.is_authenticated:
            raise NotAuthenticated
        # 404 rather than 403: someone else's board id should not
        # be confirmable. The filter runs after this.
        get_object_or_404(Dashboard, id=board, owner=self.request.user)
        return queryset
