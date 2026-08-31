from django.db.models import Count, OuterRef, Q, Subquery
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from catalog.models import Service, ServiceComponent
from catalog.serializers import (
    ComponentSerializer,
    ImportRequestSerializer,
    ServiceSerializer,
)
from common.aggregates import EventAggregateSet, StatusAggregateSet
from common.filters import FieldsBackend
from common.ordering import CURRENT_SEVERITY, WATCHER_COUNT, MappedOrderingFilter
from status.models import ComponentStatus, ServiceEvent
from status.serializers import ServiceEventSerializer


class ServiceAggregateSet(StatusAggregateSet):
    """Counts for a list of services.

    A service has no severity of its own. Its severity is the open status
    of its overall component, which is the provider's own page-level
    reading. So counting services by severity means counting those
    components, not the services.
    """

    def components(self):
        return ServiceComponent.objects.filter(
            service__in=self.queryset, is_overall=True
        )


class ServiceFilter(filters.FilterSet):
    # Declared: django-filter cannot generate a count comparison off a related set.
    tracked_component_count__gt = filters.NumberFilter(method="filter_tracked_gt")

    # Declared for a second reason. `overall_component` is not a relation
    # on Service. The current severity is not a column either. It is the
    # open row of a component's status history. So the contract's name is
    # kept, pointed at the view's `severity_now` annotation.
    overall_component__status__severity = filters.NumberFilter(
        field_name="severity_now"
    )
    overall_component__status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )

    class Meta:
        model = Service
        fields = {
            "status_page__provider": ["exact"],
            "is_featured": ["exact"],
        }

    def filter_tracked_gt(self, queryset, name, value):
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        return queryset.annotate(
            n=Count(
                "components__tracked_by",
                filter=Q(components__tracked_by__dashboard__owner=user),
                distinct=True,
            )
        ).filter(n__gt=value)


class ComponentFilter(filters.FilterSet):
    # `status` is not a relation. A component has a history of statuses
    # and the open one is current. Same contract name, same annotation.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )

    class Meta:
        model = ServiceComponent
        fields = {"is_overall": ["exact"]}


class ServiceEventFilter(filters.FilterSet):
    class Meta:
        model = ServiceEvent
        fields = {
            "kind": ["exact"],
            "phase": ["exact", "in"],
            "ends_at": ["isnull", "gte"],
            "starts_at": ["gte", "lte"],
            "affected_components": ["exact"],
        }


class ServiceViewSet(ReadOnlyModelViewSet):
    """Every read of a service, in one place.

    The list and the detail are the same resource. A component list and
    an event list belong to a service, so they are detail actions.

    Each action overrides the serializer, filters and ordering it needs.
    Those names exist on the class because DRF refuses an initkwarg that
    is not already an attribute.
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"
    serializer_class = ServiceSerializer
    aggregate_set = ServiceAggregateSet
    filterset_class = ServiceFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "updated_at"]
    # `suggested` is not a field. Severity sits behind a related path.
    #
    # Severity ahead of popularity is deliberate. A middling service
    # that is broken now beats a popular one that is fine.
    #
    # Lower severity is worse, so ascending puts the broken first. A
    # service with no reading sorts last, not as healthy.
    SUGGESTED = ["-is_featured", "severity_now", "-watcher_count", "name"]
    ordering_map = {
        "suggested": SUGGESTED,
        "overall_component__status__severity": ["severity_now"],
    }
    ordering = SUGGESTED
    # Schema generation calls get_queryset with no URL kwargs. This names
    # the model without running it.
    queryset = Service.objects.none()

    def get_queryset(self):
        queryset = Service.objects.select_related("status_page", "poller").annotate(
            watcher_count=WATCHER_COUNT,
            severity_now=Subquery(
                ComponentStatus.objects.filter(
                    component__service=OuterRef("pk"),
                    component__is_overall=True,
                    ended_at__isnull=True,
                ).values("severity")[:1]
            ),
        )
        q = self.request.query_params.get("q")
        return queryset.filter(name__icontains=q) if q else queryset

    def _page(self, queryset):
        """The same envelope the list actions return."""
        page = self.paginate_queryset(self.filter_queryset(queryset))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(responses={200: ComponentSerializer})
    @action(
        detail=True,
        url_path="components",
        url_name="components",
        serializer_class=ComponentSerializer,
        aggregate_set=StatusAggregateSet,
        filterset_class=ComponentFilter,
        ordering_fields=["name", "status_page_order", "updated_at"],
        ordering_map={"status__severity": ["severity_now"]},
        ordering=["status_page_order"],
    )
    def components(self, request, slug=None):
        return self._page(
            ServiceComponent.objects.filter(service__slug=slug)
            .select_related("service", "parent")
            .annotate(severity_now=CURRENT_SEVERITY)
        )

    @extend_schema(responses={200: ServiceEventSerializer})
    @action(
        detail=True,
        url_path="events",
        url_name="events",
        serializer_class=ServiceEventSerializer,
        aggregate_set=EventAggregateSet,
        filterset_class=ServiceEventFilter,
        ordering_fields=["starts_at", "ends_at"],
        ordering_map={},
        ordering=["-starts_at"],
    )
    def events(self, request, slug=None):
        return self._page(
            ServiceEvent.objects.filter(service__slug=slug).prefetch_related("updates")
        )


class CatalogImportView(APIView):
    """`POST /catalog/services/` is reserved.

    A future admin create takes a service body. A bulk create takes a
    list. So importing by URL gets its own path. It does not overload
    the standard collection.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=ImportRequestSerializer,
        responses={
            200: ServiceSerializer,
            201: ServiceSerializer,
            400: OpenApiResponse(description="Missing or malformed status_page_url."),
        },
    )
    def post(self, request):
        body = ImportRequestSerializer(data=request.data)
        if not body.is_valid():
            return Response(body.errors, status=400)
        service, created = Service.objects.import_from_url(
            body.validated_data["status_page_url"]
        )
        return Response(
            ServiceSerializer(service, context={"request": request}).data,
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )
