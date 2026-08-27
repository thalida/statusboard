from django.db.models import Count, OuterRef, Q, Subquery
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.import_service import import_from_url
from catalog.models import Service, ServiceComponent
from catalog.serializers import ComponentSerializer, ServiceSerializer
from common.aggregates import EventAggregateSet, StatusAggregateSet
from common.filters import FieldsBackend
from common.ordering import CURRENT_SEVERITY, MappedOrderingFilter
from status.models import ComponentStatus, ServiceEvent


class ServiceAggregateSet(StatusAggregateSet):
    def _component_queryset(self):
        return ServiceComponent.objects.filter(
            service__in=self.queryset, is_overall=True
        )


class ServiceFilter(filters.FilterSet):
    # Declared: django-filter cannot generate a count comparison off a related set.
    tracked_component_count__gt = filters.NumberFilter(method="filter_tracked_gt")

    # Declared for a second reason. `overall_component` is not a relation on
    # Service and the current severity is not a column — it is the open row of
    # a component's status history. The contract's parameter name is kept and
    # pointed at the `severity_now` annotation the view adds.
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
    # `status` is not a relation — a component has a history of statuses and
    # the open one is current. Same contract name, same annotation.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )

    class Meta:
        model = ServiceComponent
        fields = {"is_overall": ["exact"]}


class ServiceListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceSerializer
    aggregate_set = ServiceAggregateSet
    filterset_class = ServiceFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "updated_at"]
    # `suggested` is not a field. Severity sits behind a related path.
    ordering_map = {
        "suggested": ["-is_featured", "-watcher_count"],
        "overall_component__status__severity": ["severity_now"],
    }
    ordering = ["-is_featured", "-watcher_count"]

    def get_queryset(self):
        queryset = Service.objects.select_related("status_page", "poller").annotate(
            severity_now=Subquery(
                ComponentStatus.objects.filter(
                    component__service=OuterRef("pk"),
                    component__is_overall=True,
                    ended_at__isnull=True,
                ).values("severity")[:1]
            )
        )
        q = self.request.query_params.get("q")
        return queryset.filter(name__icontains=q) if q else queryset


class ServiceDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceSerializer
    lookup_field = "slug"
    queryset = Service.objects.select_related("status_page", "poller")


class ServiceComponentListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ComponentSerializer
    aggregate_set = StatusAggregateSet
    filterset_class = ComponentFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    ordering_fields = ["name", "status_page_order", "updated_at"]
    ordering_map = {"status__severity": ["severity_now"]}
    ordering = ["status_page_order"]

    def get_queryset(self):
        return (
            ServiceComponent.objects.filter(service__slug=self.kwargs["slug"])
            .select_related("service", "parent")
            .annotate(severity_now=CURRENT_SEVERITY)
        )


class ServiceEventListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    aggregate_set = EventAggregateSet
    filterset_fields = {
        "kind": ["exact"],
        "phase": ["exact", "in"],
        "ends_at": ["isnull", "gte"],
        "starts_at": ["gte", "lte"],
        "affected_components": ["exact"],
    }
    ordering_fields = ["starts_at", "ends_at"]
    ordering = ["-starts_at"]

    def get_queryset(self):
        return ServiceEvent.objects.filter(
            service__slug=self.kwargs["slug"]
        ).prefetch_related("updates")

    def get_serializer_class(self):
        from status.serializers import ServiceEventSerializer

        return ServiceEventSerializer


class CatalogImportView(APIView):
    """`POST /catalog/services/` is reserved.

    A future admin create takes a service body and a bulk create takes a
    list, so importing by URL gets its own path rather than overloading
    the standard collection.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        url = (request.data.get("url") or "").strip()
        if not url:
            return Response({"detail": "url is required"}, status=400)
        service, created = import_from_url(url)
        return Response(
            ServiceSerializer(service, context={"request": request}).data,
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )
