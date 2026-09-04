"""Every read of a component, in one place.

Discover, a service's Components tab, a component's descendants and an
event's affected list are one collection with different parameters. Four
nested routes would have been four copies of this queryset.
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny

from catalog.filters import ComponentFilter
from catalog.models import ServiceComponent
from catalog.queries import COMPONENT_WATCHER_COUNT
from catalog.serializers import ComponentSerializer
from common.aggregates import StatusAggregateSet
from common.filters import REJECTED_PARAMETER, FieldsBackend
from common.ordering import MappedOrderingFilter
from common.serializers import ErrorSerializer
from status.queries import CURRENT_SEVERITY


class ComponentQueryMixin:
    permission_classes = [AllowAny]
    serializer_class = ComponentSerializer
    # get_queryset reads the request, which schema generation has not
    # set. This names the model without running it.
    queryset = ServiceComponent.objects.none()

    def get_queryset(self):
        return (
            ServiceComponent.objects.visible()
            .for_display(self.request.user)
            .annotate(
                severity_now=CURRENT_SEVERITY,
                watcher_count=COMPONENT_WATCHER_COUNT,
            )
            .distinct()
        )


@extend_schema_view(
    get=extend_schema(
        responses={
            200: ComponentSerializer,
            400: OpenApiResponse(description=REJECTED_PARAMETER),
        }
    )
)
class ComponentListView(ComponentQueryMixin, generics.ListAPIView):
    aggregate_set = StatusAggregateSet
    filterset_class = ComponentFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    ordering_fields = ["name", "status_page_order", "updated_at"]
    # Severity ahead of popularity, the same as the service sort this
    # replaces. Lower severity is worse, so ascending puts the broken
    # first.
    SUGGESTED = ["-is_featured", "severity_now", "-watcher_count", "name"]
    ordering_map = {
        "suggested": SUGGESTED,
        "status__severity": ["severity_now"],
    }
    ordering = SUGGESTED

    def initial(self, request, *args, **kwargs):
        """Pick the default sort from what the caller asked for.

        DRF reads `ordering` as an attribute, so a method cannot supply
        it. It does not check a default against `ordering_fields`
        either, so neither branch below needs an entry there.
        """
        super().initial(request, *args, **kwargs)
        if request.query_params.get("q"):
            # The rollup leads, then the suggested keys. Typing a
            # service's name matches every part of it. Without this,
            # eighty rows bury the one that answers the question.
            self.ordering = ["-is_overall", *self.SUGGESTED]
        elif request.query_params.get("service"):
            # A service tab reads down the provider's own page.
            self.ordering = ["status_page_order"]

    def filter_queryset(self, queryset):
        """Narrow to what the caller typed, before the backends run.

        One control and one label, Smart, on every list. A separate
        "best match" would name a ranking the search does not work out.
        """
        q = self.request.query_params.get("q")
        if q:
            queryset = queryset.search(q)
        return super().filter_queryset(queryset)


@extend_schema_view(
    get=extend_schema(responses={200: ComponentSerializer, 404: ErrorSerializer})
)
class ComponentDetailView(ComponentQueryMixin, generics.RetrieveAPIView):
    filter_backends = [FieldsBackend]
    lookup_field = "pk"
    # The contract names the path variable `uuid`. DRF renames a `pk`
    # one to `id`, which would document a path nothing serves.
    lookup_url_kwarg = "uuid"
