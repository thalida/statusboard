from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.mixins import FieldsMixin
from status.models import ComponentStatus, EventUpdate, ServiceEvent


def _service_ref_serializer():
    # Imported lazily. catalog imports status, so a module-level import
    # here would be a cycle.
    from catalog.serializers import ServiceRefSerializer

    return ServiceRefSerializer


class StatusSerializer(FieldsMixin, serializers.ModelSerializer):
    last_refreshed_at = serializers.SerializerMethodField()

    class Meta:
        model = ComponentStatus
        fields = ["severity", "source", "started_at", "ended_at", "last_refreshed_at"]

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_refreshed_at(self, row):
        poller = getattr(row.component.service, "poller", None)
        return poller.last_success_at if poller else None


class EventRefSerializer(FieldsMixin, serializers.ModelSerializer):
    """An event as it appears on a component.

    There is no `updates` array. A list row costs one title, not a log.
    """

    class Meta:
        model = ServiceEvent
        fields = ["id", "kind", "title", "phase", "starts_at", "ends_at"]


class EventUpdateSerializer(FieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = EventUpdate
        fields = ["phase", "body", "posted_at", "source"]


class ServiceEventSerializer(FieldsMixin, serializers.ModelSerializer):
    """One row of the feed. The log is `/events/{uuid}/updates/`."""

    class Meta:
        model = ServiceEvent
        fields = [
            "id",
            "kind",
            "title",
            "phase",
            "starts_at",
            "ends_at",
            "detected_by",
            "service",
        ]

    def get_fields(self):
        # `catalog.serializers` imports this module for `EventRefSerializer`,
        # so the reverse import has to wait until both have finished loading.
        fields = super().get_fields()
        fields["service"] = _service_ref_serializer()(read_only=True)
        return fields


class ServiceEventDetailSerializer(ServiceEventSerializer):
    """The event screen's header and its About tab.

    Both counts are here because the header draws both tab badges
    before either tab has made a request.
    """

    update_count = serializers.SerializerMethodField()
    affected_count = serializers.SerializerMethodField()
    last_update_at = serializers.SerializerMethodField()

    class Meta(ServiceEventSerializer.Meta):
        fields = [
            *ServiceEventSerializer.Meta.fields,
            "update_count",
            "affected_count",
            "last_update_at",
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_update_count(self, event):
        return event.updates.count()

    @extend_schema_field(serializers.IntegerField())
    def get_affected_count(self, event):
        # `visible`, because the Affects tab reads `?event=` and counts
        # the same rows. The badge cannot say 2 above a list of one.
        return event.affected_components.visible().count()

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_update_at(self, event):
        newest = event.updates.order_by("-posted_at").first()
        return newest.posted_at if newest else None
