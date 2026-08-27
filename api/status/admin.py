from django.contrib import admin
from unfold.admin import ModelAdmin

from status.models import ComponentStatus, EventUpdate, PollRun, ServiceEvent


@admin.register(PollRun)
class PollRunAdmin(ModelAdmin):
    """We are the thing that tells you when services break.

    So we cannot quietly break ourselves: a service failing N consecutive
    polls is visibly flagged rather than silently showing stale green.
    """

    list_display = ["poller", "provider", "started_at", "ok"]
    list_filter = ["ok", "provider"]
    readonly_fields = ["error"]


@admin.register(ComponentStatus)
class ComponentStatusAdmin(ModelAdmin):
    list_display = ["component", "severity", "source", "started_at", "ended_at"]
    list_filter = ["severity", "source"]


@admin.register(ServiceEvent)
class ServiceEventAdmin(ModelAdmin):
    list_display = ["title", "service", "kind", "phase", "starts_at", "ends_at"]
    list_filter = ["kind", "phase"]


@admin.register(EventUpdate)
class EventUpdateAdmin(ModelAdmin):
    list_display = ["event", "phase", "posted_at"]
