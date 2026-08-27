from rest_framework import serializers

from common.mixins import FieldsMixin
from status.models import ComponentStatus, EventUpdate, ServiceEvent


class StatusSerializer(FieldsMixin, serializers.ModelSerializer):
    last_refreshed_at = serializers.SerializerMethodField()

    class Meta:
        model = ComponentStatus
        fields = ["severity", "source", "started_at", "ended_at", "last_refreshed_at"]

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
        fields = ["phase", "body", "posted_at"]


class ServiceEventSerializer(FieldsMixin, serializers.ModelSerializer):
    updates = EventUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceEvent
        fields = ["id", "kind", "title", "phase", "starts_at", "ends_at", "updates"]
