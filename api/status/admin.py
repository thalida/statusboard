from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_celery_beat.admin import (
    ClockedScheduleAdmin,
    CrontabScheduleAdmin,
    IntervalScheduleAdmin,
    PeriodicTaskAdmin,
    SolarScheduleAdmin,
)
from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    SolarSchedule,
)
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    RangeDateTimeFilter,
)
from unfold.decorators import display

from catalog.admin import SEVERITY_VARIANTS, _severity_label
from common.admin import BaseModelAdmin
from status.choices import CLOSED_PHASES, EventKind
from status.models import ComponentStatus, EventUpdate, PollRun, ServiceEvent


@admin.register(PollRun)
class PollRunAdmin(BaseModelAdmin, ModelAdmin):
    """We are the thing that tells you when services break.

    So we cannot quietly break ourselves. A failing poll is a labelled row
    here, not a number to go looking for.
    """

    list_display = ["poller", "display_ok", "provider", "started_at", "display_error"]
    date_hierarchy = "started_at"
    search_fields = ["poller__service__name", "url", "error"]
    list_filter = [
        "ok",
        ("provider", ChoicesDropdownFilter),
        ("poller__service", AutocompleteSelectFilter),
        ("started_at", RangeDateTimeFilter),
    ]
    ordering = ["-started_at"]
    readonly_fields = ["error"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("poller__service")

    @display(
        description=_("Result"),
        label={"OK": "success", "Failed": "danger"},
        ordering="ok",
    )
    def display_ok(self, obj):
        return "OK" if obj.ok else "Failed"

    @display(description=_("Error"))
    def display_error(self, obj):
        return (obj.error or "—")[:90]


@admin.register(ComponentStatus)
class ComponentStatusAdmin(BaseModelAdmin, ModelAdmin):
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
        return _severity_label(obj.severity)


@admin.register(ServiceEvent)
class ServiceEventAdmin(BaseModelAdmin, ModelAdmin):
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
class EventUpdateAdmin(BaseModelAdmin, ModelAdmin):
    list_display = ["event", "phase", "posted_at"]
    date_hierarchy = "posted_at"
    search_fields = ["event__title", "body"]
    list_filter = [("posted_at", RangeDateTimeFilter)]
    autocomplete_fields = ["event"]


# Unfold ships no contrib module for django-celery-beat. Its admin classes
# subclass Django's own ModelAdmin, so its screens render unstyled beside
# every other one. The documented remedy is to re-register them. PeriodicTask
# is where the polling schedule is read, so it should not look like a
# different product.
#
# django_celery_beat precedes this app in INSTALLED_APPS, so its admin is
# already registered by the time this runs.
RESTYLED_BEAT_ADMIN = [
    (PeriodicTask, PeriodicTaskAdmin),
    (IntervalSchedule, IntervalScheduleAdmin),
    (CrontabSchedule, CrontabScheduleAdmin),
    (SolarSchedule, SolarScheduleAdmin),
    (ClockedSchedule, ClockedScheduleAdmin),
]

for _model, _base in RESTYLED_BEAT_ADMIN:
    admin.site.unregister(_model)
    admin.site.register(
        _model, type(f"Unfold{_base.__name__}", (_base, ModelAdmin), {})
    )
