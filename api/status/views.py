"""Every read of an event, in one place.

Home, a service and a component show the same feed at different scopes.
The screens call it Updates. This names the model, and `/meta/`
publishes the labels.
"""

import uuid

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny

from common.aggregates import EventAggregateSet
from common.filters import FieldsBackend
from common.ordering import MappedOrderingFilter
from common.pagination import TimelinePagination
from common.serializers import ErrorSerializer
from dashboards.models import Dashboard
from status.filters import EventFilter
from status.models import EventUpdate, ServiceEvent
from status.serializers import (
    EventUpdateSerializer,
    ServiceEventDetailSerializer,
    ServiceEventSerializer,
)


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
        queryset = ServiceEvent.objects.select_related("service")
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


@extend_schema_view(
    get=extend_schema(
        responses={200: ServiceEventDetailSerializer, 404: ErrorSerializer}
    )
)
class EventDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceEventDetailSerializer
    filter_backends = [FieldsBackend]
    lookup_field = "pk"
    # The contract names the path variable `uuid`. DRF renames a `pk`
    # one to `id`, which would document a path nothing serves.
    lookup_url_kwarg = "uuid"
    queryset = ServiceEvent.objects.select_related("service")


class EventUpdateListView(generics.ListAPIView):
    """One event's log, oldest first.

    The feed is newest first because it is a feed. This is a
    narrative, and a narrative is read forwards.
    """

    permission_classes = [AllowAny]
    serializer_class = EventUpdateSerializer
    filter_backends = [FieldsBackend]
    pagination_class = TimelinePagination
    # get_queryset reads self.kwargs, which schema generation has not
    # set. This names the model without running it.
    queryset = EventUpdate.objects.none()

    def get_queryset(self):
        event = get_object_or_404(ServiceEvent, pk=self.kwargs["uuid"])
        # `TimelinePagination.ordering` is what actually orders the
        # response: CursorPagination always re-sorts by it. This is
        # the correct order regardless, in case pagination is ever off.
        return event.updates.order_by("posted_at")
