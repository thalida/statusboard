from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    RangeDateTimeFilter,
)
from unfold.decorators import display

from common.admin import SEVERITY_VARIANTS, PollerWrittenAdmin, severity_label
from status.choices import CLOSED_PHASES, EventKind
from status.models import ComponentStatus, EventUpdate, ServiceEvent


@admin.register(ComponentStatus)
class ComponentStatusAdmin(PollerWrittenAdmin, ModelAdmin):
    list_display = ["component", "display_severity", "source", "started_at", "ended_at"]
    date_hierarchy = "started_at"
    search_fields = ["component__name", "component__service__name"]
    list_filter = [
        ("severity", ChoicesDropdownFilter),
        ("source", ChoicesDropdownFilter),
        ("started_at", RangeDateTimeFilter),
        ("ended_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["component"]
    ordering = ["-started_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("component__service")

    @display(description=_("Severity"), label=SEVERITY_VARIANTS, ordering="severity")
    def display_severity(self, obj):
        return severity_label(obj.severity)


class EventUpdateInline(TabularInline):
    """The provider's update log, read only.

    These are the provider's words, written by a poll. Editing them here
    would make the admin disagree with the status page it mirrors.
    """

    model = EventUpdate
    tab = True
    extra = 0
    max_num = 0
    can_delete = False
    per_page = 10
    fields = ["phase", "body", "posted_at"]
    readonly_fields = fields
    ordering = ["-posted_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceEvent)
class ServiceEventAdmin(PollerWrittenAdmin, ModelAdmin):
    list_display = ["title", "service", "display_kind", "display_phase", "starts_at"]
    date_hierarchy = "starts_at"
    search_fields = ["title", "service__name", "external_id"]
    list_filter = [
        ("kind", ChoicesDropdownFilter),
        ("service", AutocompleteSelectFilter),
        ("starts_at", RangeDateTimeFilter),
        ("ends_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["service"]
    filter_horizontal = ["affected_components"]
    ordering = ["-starts_at"]
    inlines = [EventUpdateInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("service")

    @display(
        description=_("Kind"),
        label={
            EventKind.INCIDENT.label: "danger",
            EventKind.MAINTENANCE.label: "info",
        },
        ordering="kind",
    )
    def display_kind(self, obj):
        return EventKind(obj.kind).label

    @display(description=_("Phase"), label=True, ordering="phase")
    def display_phase(self, obj):
        # A closed phase means the event is over.
        return obj.phase.replace("_", " ").title()

    @display(description=_("Open"), boolean=True)
    def display_open(self, obj):
        return obj.phase not in CLOSED_PHASES


@admin.register(EventUpdate)
class EventUpdateAdmin(PollerWrittenAdmin, ModelAdmin):
    list_display = ["event", "phase", "posted_at"]
    date_hierarchy = "posted_at"
    search_fields = ["event__title", "body"]
    list_filter = [("posted_at", RangeDateTimeFilter)]
    autocomplete_fields = ["event"]
