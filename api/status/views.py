"""Every read of an event, in one place.

Home, a service and a component show the same feed at different scopes.
The screens call it Updates. This names the model, and `/meta/`
publishes the labels.
"""

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny

from common.aggregates import EventAggregateSet
from common.filters import REJECTED_PARAMETER, FieldsBackend
from common.ordering import MappedOrderingFilter
from common.pagination import TimelinePagination
from common.serializers import ErrorSerializer
from status.filters import EventFilter
from status.models import EventUpdate, ServiceEvent
from status.serializers import (
    EventUpdateSerializer,
    ServiceEventDetailSerializer,
    ServiceEventSerializer,
)


@extend_schema_view(
    get=extend_schema(
        responses={
            200: ServiceEventSerializer,
            400: OpenApiResponse(description=REJECTED_PARAMETER),
        }
    )
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
    # `EventFilter.filter_dashboard` narrows this to one board, and
    # decides whether the caller owns it.
    queryset = ServiceEvent.objects.select_related("service")


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
