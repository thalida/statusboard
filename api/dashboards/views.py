from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ServiceComponent
from catalog.serializers import ComponentSerializer
from common.aggregates import StatusAggregateSet
from common.filters import FieldsBackend
from common.ordering import CURRENT_SEVERITY, NEXT_TRANSITION, MappedOrderingFilter
from dashboards.filters import BoardComponentFilter
from dashboards.models import Dashboard, DashboardItem
from dashboards.serializers import TrackComponentSerializer


def _board(request, uuid):
    # 404 rather than 403: someone else's board id should not be confirmable.
    return get_object_or_404(Dashboard, id=uuid, owner=request.user)


class BoardComponentListView(generics.ListCreateAPIView):
    # get_queryset reads self.kwargs, which schema generation has
    # not set. This names the model without running it.
    queryset = ServiceComponent.objects.none()
    permission_classes = [IsAuthenticated]
    serializer_class = ComponentSerializer
    aggregate_set = StatusAggregateSet
    filterset_class = BoardComponentFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    ordering_fields = ["name", "updated_at"]
    # `next_transition` is not a field. Severity sits behind a related path.
    ordering_map = {
        "status__severity": ["severity_now"],
        "next_transition": ["next_transition"],
    }
    ordering = ["severity_now"]  # worst first: lower severity is worse

    def get_queryset(self):
        board = _board(self.request, self.kwargs["uuid"])
        return (
            ServiceComponent.objects.filter(tracked_by__dashboard=board)
            .select_related("service", "parent")
            .annotate(severity_now=CURRENT_SEVERITY, next_transition=NEXT_TRANSITION)
            .distinct()
        )

    @extend_schema(
        request=TrackComponentSerializer,
        responses={
            201: ComponentSerializer,
            200: OpenApiResponse(
                response=ComponentSerializer,
                description="Already tracked. Tracking twice is not an error.",
            ),
        },
    )
    def create(self, request, *args, **kwargs):
        board = _board(request, self.kwargs["uuid"])
        component = get_object_or_404(
            ServiceComponent, id=request.data.get("component_id")
        )
        # DashboardItem.save keeps the service's watcher count true.
        _, created = DashboardItem.objects.get_or_create(
            dashboard=board, component=component
        )
        return Response(
            ComponentSerializer(component, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BoardComponentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            204: OpenApiResponse(description="No longer tracked."),
            404: OpenApiResponse(description="Not on this board."),
        }
    )
    def delete(self, request, uuid, component_id):
        board = _board(request, uuid)
        item = get_object_or_404(
            DashboardItem, dashboard=board, component_id=component_id
        )
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
