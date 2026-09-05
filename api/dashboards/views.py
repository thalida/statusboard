from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ServiceComponent
from catalog.serializers import ComponentSerializer
from common.aggregates import StatusAggregateSet
from common.filters import REJECTED_PARAMETER, FieldsBackend
from common.ordering import MappedOrderingFilter
from dashboards.filters import BoardComponentFilter
from dashboards.models import Dashboard, DashboardItem
from dashboards.serializers import TrackComponentSerializer
from status.queries import CURRENT_SEVERITY, NEXT_TRANSITION


def _board(request, uuid):
    # 404 rather than 403: someone else's board id should not be confirmable.
    return get_object_or_404(Dashboard, id=uuid, owner=request.user)


# On `post`, not on `create`. The generator reads the handler the router
# dispatches to. An annotation on `create` was dropped in silence, so
# the documented 200 and 404 reached no schema.
@extend_schema_view(
    get=extend_schema(
        responses={
            200: ComponentSerializer,
            400: OpenApiResponse(description=REJECTED_PARAMETER),
        }
    ),
    post=extend_schema(
        request=TrackComponentSerializer,
        responses={
            201: ComponentSerializer,
            200: OpenApiResponse(
                response=ComponentSerializer,
                description="Already tracked. Tracking twice is not an error.",
            ),
            404: OpenApiResponse(description="No such board, or no such component."),
        },
    ),
)
class BoardComponentListView(generics.ListCreateAPIView):
    # Schema generation reads the model off this before it calls
    # get_queryset. It names the model without running one.
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
        rows = ServiceComponent.objects.visible().annotate(
            severity_now=CURRENT_SEVERITY, next_transition=NEXT_TRANSITION
        )
        if "uuid" not in self.kwargs:
            # Schema generation reaches here with no URL. It reads the
            # annotations, because the filters and the sorts name them.
            return rows.none()
        board = _board(self.request, self.kwargs["uuid"])
        return (
            rows.filter(tracked_by__dashboard=board)
            .for_display(self.request.user)
            .distinct()
        )

    def create(self, request, *args, **kwargs):
        board = _board(request, self.kwargs["uuid"])
        # `visible`, so a write agrees with the reads. An archived id
        # already answers 404 on the component detail. Accepting it here
        # made a board row that no list renders.
        component = get_object_or_404(
            ServiceComponent.objects.visible(), id=request.data.get("component_id")
        )
        _, created = DashboardItem.objects.get_or_create(
            dashboard=board,
            component=component,
            defaults={"created_by": request.user, "updated_by": request.user},
        )
        # Read again, after the write. `ComponentSerializer` reads the
        # counts `for_display` annotates, and `is_tracked` is false
        # until the item exists.
        row = (
            ServiceComponent.objects.visible()
            .for_display(request.user)
            .get(pk=component.pk)
        )
        return Response(
            ComponentSerializer(row, context={"request": request}).data,
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
