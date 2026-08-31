from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from catalog.models import Service, ServiceComponent, StatusPage
from common.mixins import FieldsMixin
from polling.models import Poller
from status.choices import EventKind
from status.serializers import EventRefSerializer, StatusSerializer


class StatusPageSerializer(FieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = StatusPage
        fields = ["url", "provider"]


class PollerSerializer(FieldsMixin, serializers.ModelSerializer):
    interval_seconds = serializers.IntegerField(source="effective_interval_seconds")
    cooldown_seconds = serializers.IntegerField(source="effective_cooldown_seconds")

    class Meta:
        model = Poller
        fields = [
            "interval_seconds",
            "cooldown_seconds",
            "last_success_at",
            "next_at",
            "consecutive_failure_count",
            "is_paused",
        ]


class ServiceRefSerializer(FieldsMixin, serializers.ModelSerializer):
    """Breaks the Service -> Component -> Service cycle. It nests nothing."""

    class Meta:
        model = Service
        fields = ["id", "slug", "name", "logo"]


class PathNodeSerializer(serializers.ModelSerializer):
    """One step above a component, enough to link to it.

    A joined string named the ancestors and gave a client nothing to
    click. This is the id, the name, and whether the step is the service
    rollup. A client draws that step as the service itself.
    """

    class Meta:
        model = ServiceComponent
        fields = ["id", "name", "is_overall"]


class ComponentSerializer(FieldsMixin, serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    child_count = serializers.SerializerMethodField()
    upcoming_maintenance = serializers.SerializerMethodField()
    upcoming_maintenance_count = serializers.SerializerMethodField()
    active_incident = serializers.SerializerMethodField()
    active_incident_count = serializers.SerializerMethodField()
    service = ServiceRefSerializer(read_only=True)
    is_tracked = serializers.SerializerMethodField()

    class Meta:
        model = ServiceComponent
        fields = [
            "id",
            "name",
            "path",
            "parent",
            "child_count",
            "is_overall",
            "archived_at",
            "status",
            "upcoming_maintenance",
            "upcoming_maintenance_count",
            "active_incident",
            "active_incident_count",
            "service",
            "is_tracked",
        ]

    @extend_schema_field(StatusSerializer(allow_null=True))
    def get_status(self, row):
        current = row.statuses.filter(ended_at__isnull=True).first()
        return (
            StatusSerializer(
                current,
                context=self.context,
                fields_tree=self.child_tree("status"),
            ).data
            if current
            else None
        )

    @extend_schema_field(PathNodeSerializer(many=True))
    def get_path(self, row):
        # Top down, and empty on the overall component: it is under
        # nothing. Empty rather than null, so a client maps over it
        # without checking first.
        #
        # `ancestors` walks the chain and guards the loop a self
        # referencing column allows. This walked it a second time and
        # did not.
        if row.is_overall:
            return []
        return PathNodeSerializer(row.ancestors, many=True).data

    @extend_schema_field(serializers.IntegerField())
    def get_child_count(self, row):
        return 0 if row.is_overall else row.children.count()

    @extend_schema_field(EventRefSerializer(allow_null=True))
    def get_upcoming_maintenance(self, row):
        soonest = row.events.live(EventKind.MAINTENANCE).order_by("starts_at").first()
        return (
            EventRefSerializer(
                soonest,
                context=self.context,
                fields_tree=self.child_tree("upcoming_maintenance"),
            ).data
            if soonest
            else None
        )

    @extend_schema_field(serializers.IntegerField())
    def get_upcoming_maintenance_count(self, row):
        return row.events.live(EventKind.MAINTENANCE).count()

    @extend_schema_field(EventRefSerializer(allow_null=True))
    def get_active_incident(self, row):
        newest = row.events.live(EventKind.INCIDENT).order_by("-starts_at").first()
        return (
            EventRefSerializer(
                newest,
                context=self.context,
                fields_tree=self.child_tree("active_incident"),
            ).data
            if newest
            else None
        )

    @extend_schema_field(serializers.IntegerField())
    def get_active_incident_count(self, row):
        return row.events.live(EventKind.INCIDENT).count()

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_is_tracked(self, row):
        user = getattr(self.context.get("request"), "user", None)
        if user is None or not user.is_authenticated:
            return None
        return row.boards.filter(owner=user).exists()


class ServiceSerializer(FieldsMixin, serializers.ModelSerializer):
    status_page = StatusPageSerializer(read_only=True)
    poller = PollerSerializer(read_only=True)
    overall_component = serializers.SerializerMethodField()
    component_count = serializers.SerializerMethodField()
    tracked_component_count = serializers.SerializerMethodField()
    in_catalog_since = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "slug",
            "name",
            "description",
            "homepage_url",
            "logo",
            "in_catalog_since",
            "component_count",
            "status_page",
            "poller",
            "overall_component",
            "tracked_component_count",
        ]

    @extend_schema_field(ComponentSerializer(allow_null=True))
    def get_overall_component(self, service):
        row = service.components.filter(is_overall=True).first()
        return (
            ComponentSerializer(
                row,
                context=self.context,
                fields_tree=self.child_tree("overall_component"),
            ).data
            if row
            else None
        )

    @extend_schema_field(serializers.IntegerField())
    def get_component_count(self, service):
        # The overall component is excluded: it is the service, not a part of it.
        return service.components.filter(is_overall=False, is_archived=False).count()

    @extend_schema_field(serializers.IntegerField())
    def get_tracked_component_count(self, service):
        user = getattr(self.context.get("request"), "user", None)
        if user is None or not user.is_authenticated:
            return 0
        return (
            ServiceComponent.objects.filter(service=service, boards__owner=user)
            .distinct()
            .count()
        )


class ImportRequestSerializer(serializers.Serializer):
    """The body of POST /catalog/import/.

    Named `status_page_url`, not `url`, because that is what the contract
    documents and the contract is what the client is written against.
    """

    status_page_url = serializers.URLField()

    def validate_status_page_url(self, value):
        """Refuse an address we will not fetch, here rather than deeper.

        The session guards every hop, so this changes no outcome. It
        makes the ordinary mistake a 400 with a reason instead of a
        failure raised out of the adapter probe.
        """
        from polling.fetch import BlockedAddress, check

        try:
            check(value)
        except BlockedAddress as error:
            raise serializers.ValidationError(str(error)) from error
        return value
