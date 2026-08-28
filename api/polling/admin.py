from django.contrib import admin
from django.urls import reverse
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
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
)
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from catalog.models import ServiceComponent
from common.admin import (
    BaseModelAdmin,
    InheritedDefaultsMixin,
    PollerWrittenAdmin,
    audit_section,
    change_link,
    filtered_list,
    record_column,
    related_count,
)
from polling.models import Poller, PollRun
from status.models import ComponentStatus, ServiceEvent


class PollRunColumns:
    """How a run reads. The same on its own table and under a poller."""

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

    @display(description=_("Took"), ordering="finished_at")
    def display_took(self, obj):
        # A provider that has become slow shows here first. A run that
        # never finished has no answer, which is itself the answer.
        if obj.finished_at is None or obj.started_at is None:
            return "—"
        return f"{(obj.finished_at - obj.started_at).total_seconds():.1f}s"


class PollRunInline(PollRunColumns, TabularInline):
    """The poller's own log, read only.

    A poller is opened to find out whether it is working, and this is
    what answers that. `poll_service` writes these rows.
    """

    model = PollRun
    tab = True
    verbose_name = _("Poll run")
    verbose_name_plural = _("Poll runs")
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True
    per_page = 20
    fields = ["display_ok", "provider", "started_at", "finished_at", "display_error"]
    readonly_fields = fields
    ordering = ["-started_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Poller)
class PollerAdmin(
    InheritedDefaultsMixin, BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin
):
    """Where a stalled poller is supposed to be obvious.

    A service that stops being polled shows every board a stale green,
    which is worse than showing nothing.
    """

    list_display = [
        "display_poller",
        "display_service",
        "display_health",
        "is_paused",
        "display_interval",
        "consecutive_failure_count",
        "last_success_at",
        "next_at",
        "display_related",
    ]
    search_fields = ["service__name", "service__slug", "note"]
    list_filter = [
        ("service", AutocompleteSelectFilter),
        "is_paused",
        ("consecutive_failure_count", RangeNumericFilter),
        ("interval_seconds", RangeNumericFilter),
        ("last_success_at", RangeDateTimeFilter),
        ("next_at", RangeDateTimeFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["service"]
    ordering = ["-consecutive_failure_count", "next_at"]
    inlines = [PollRunInline]
    fieldsets = [
        (None, {"fields": ["service", "is_paused", "note"]}),
        (
            _("Tuning"),
            {
                "fields": [
                    "interval_seconds",
                    "cooldown_seconds",
                    "max_interval_seconds",
                ]
            },
        ),
        (
            _("Health"),
            {"fields": ["next_at", "last_success_at", "consecutive_failure_count"]},
        ),
        audit_section(),
    ]
    display_poller = record_column(_("Poller"))
    actions_row = ["poll_now", "toggle_pause"]
    actions_detail = ["poll_now", "toggle_pause"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("service")
            .annotate(
                run_count=related_count(PollRun.objects, "poller"),
                component_count=related_count(
                    ServiceComponent.objects, "service", ref="service_id"
                ),
            )
        )

    @display(description=_("Service"), ordering="service__name")
    def display_service(self, obj):
        return change_link(obj.service)

    @display(description=_("Interval"), ordering="interval_seconds")
    def display_interval(self, obj):
        # What it actually polls at. The column is blank when the poller
        # takes the deployment default, so the number was not readable
        # from the table at all.
        return f"{obj.effective_interval_seconds}s"

    def has_add_permission(self, request):
        """There is never a service without one, so there is none to add.

        A signal on Service creates it, and the column is one-to-one, so
        the form could only offer a duplicate the database refuses.
        """
        return False

    @display(description=_("View"), dropdown=True)
    def display_related(self, obj):
        return {
            "title": _("Related"),
            "items": [
                {
                    "title": _("Service"),
                    "link": reverse(
                        "admin:catalog_service_change", args=[obj.service_id]
                    ),
                },
                filtered_list(
                    "admin:polling_pollrun_changelist",
                    _("Poll runs"),
                    obj.run_count,
                    poller__service__id__exact=obj.service_id,
                ),
                filtered_list(
                    "admin:catalog_servicecomponent_changelist",
                    _("Components"),
                    obj.component_count,
                    service__id__exact=obj.service_id,
                ),
            ],
        }

    @display(
        description=_("Health"),
        label={"Paused": "info", "Healthy": "success", "Failing": "danger"},
    )
    def display_health(self, obj):
        if obj.is_paused:
            return "Paused"
        return "Failing" if obj.consecutive_failure_count else "Healthy"

    @action(
        description=_("Poll now"),
        icon="sync",
        url_path="poll-now",
        variant=ActionVariant.PRIMARY,
        permissions=["manage"],
    )
    def poll_now(self, request, object_id):
        from polling.tasks import poll_service

        poller = Poller.objects.get(pk=object_id)
        poll_service.delay(str(poller.service_id))
        self.message_user(request, _("Queued a poll."))

    @action(
        description=_("Pause / resume"),
        icon="pause",
        url_path="toggle-pause",
        permissions=["manage"],
    )
    def toggle_pause(self, request, object_id):
        poller = Poller.objects.get(pk=object_id)
        poller.is_paused = not poller.is_paused
        poller.save(update_fields=["is_paused"])
        self.message_user(request, _("Paused.") if poller.is_paused else _("Resumed."))

    def has_manage_permission(self, request, obj=None):
        return request.user.has_perm("catalog.change_poller")


@admin.register(PollRun)
class PollRunAdmin(PollRunColumns, PollerWrittenAdmin, ModelAdmin):
    """We are the thing that tells you when services break.

    So we cannot quietly break ourselves. A failing poll is a labelled row
    here, not a number to go looking for.
    """

    list_display = [
        "display_run",
        "display_poller",
        "display_service",
        "display_ok",
        "provider",
        "started_at",
        "display_took",
        "display_error",
        "display_related",
    ]
    date_hierarchy = "started_at"
    search_fields = [
        "poller__service__name",
        "poller__service__slug",
        "url",
        "error",
    ]
    list_filter = [
        ("poller__service", AutocompleteSelectFilter),
        ("poller", AutocompleteSelectFilter),
        "ok",
        ("provider", ChoicesDropdownFilter),
        ("started_at", RangeDateTimeFilter),
        ("finished_at", RangeDateTimeFilter),
    ]
    ordering = ["-started_at"]
    readonly_fields = ["error"]
    fieldsets = [
        (None, {"fields": ["poller", "url", "provider"]}),
        (_("Result"), {"fields": ["ok", "error"]}),
        (_("Timing"), {"fields": ["started_at", "finished_at"]}),
        audit_section(),
    ]
    display_run = record_column(_("Poll run"))

    def get_queryset(self, request):
        # The counts are what make the `Wrote` links worth opening. Read
        # without them, every run offers two links and only some of them
        # lead anywhere.
        return (
            super()
            .get_queryset(request)
            .select_related("poller__service")
            .annotate(
                status_count=related_count(ComponentStatus.objects, "poll_run"),
                event_count=related_count(ServiceEvent.objects, "poll_run"),
            )
        )

    @display(description=_("Poller"), ordering="poller__service__name")
    def display_poller(self, obj):
        return change_link(obj.poller)

    @display(description=_("Service"), ordering="poller__service__name")
    def display_service(self, obj):
        return change_link(obj.poller.service)

    @display(description=_("View"), dropdown=True)
    def display_related(self, obj):
        """What the run wrote.

        A run is only worth opening for what it did to the tables. Read
        without this you can see a reading came from a run and not the
        rest of what that same run changed.
        """
        return {
            "title": _("Wrote"),
            "items": [
                filtered_list(
                    "admin:status_componentstatus_changelist",
                    _("Statuses (%d)") % obj.status_count,
                    poll_run__id__exact=obj.pk,
                ),
                filtered_list(
                    "admin:status_serviceevent_changelist",
                    _("Events (%d)") % obj.event_count,
                    poll_run__id__exact=obj.pk,
                ),
            ],
        }


# Unfold ships no contrib module for django-celery-beat. Its admin classes
# subclass Django's own ModelAdmin, so its screens render unstyled beside
# every other one. The documented remedy is to re-register them. PeriodicTask
# is where the polling schedule is read, so it should not look like a
# different product.
#
# django_celery_beat precedes this app in INSTALLED_APPS, so its admin is
# already registered by the time this runs.
class PollingScheduleAdmin(PeriodicTaskAdmin):
    """The schedule the poller runs on. Only the pause belongs to a person.

    A second task on the same job doubles every poll of every provider. A
    changed argument, queue or routing key sends the worker somewhere
    that does not exist. Neither one fails where anybody sees it. Turning
    the schedule off is the safe control, so it is the only one open.

    The schedule itself is set up by `polling.setup`, which is also what
    puts it back if it goes missing.
    """

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # `regtask` is a picker that rewrites `task`. Readonly it cannot be
    # rendered at all — Django drops a readonly field from the form and
    # then cannot resolve it, which is a 500 on the change page. It is
    # dropped from the form instead, and nothing is lost: `task` is
    # right below it and says the same thing.
    HIDDEN = {"regtask"}

    def get_fieldsets(self, request, obj=None):
        return [
            (
                name,
                {
                    **options,
                    "fields": [f for f in options["fields"] if f not in self.HIDDEN],
                },
            )
            for name, options in self.fieldsets
        ]

    def get_readonly_fields(self, request, obj=None):
        # Read the names off the fieldsets, not the model, so a form-only
        # field is covered too.
        named = [n for _, o in self.get_fieldsets(request, obj) for n in o["fields"]]
        return [name for name in named if name != "enabled"]


RESTYLED_BEAT_ADMIN = [
    (PeriodicTask, PollingScheduleAdmin),
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
