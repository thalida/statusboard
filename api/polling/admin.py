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
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
)
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from common.admin import (
    BaseModelAdmin,
    InheritedDefaultsMixin,
    PollerWrittenAdmin,
    change_link,
    filtered_list,
)
from polling.models import Poller, PollRun


@admin.register(Poller)
class PollerAdmin(
    InheritedDefaultsMixin, BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin
):
    """Where a stalled poller is supposed to be obvious.

    A service that stops being polled shows every board a stale green,
    which is worse than showing nothing.
    """

    # First column is plain: Django turns it into the link to this record.
    list_display = [
        "service",
        "display_health",
        "consecutive_failure_count",
        "last_success_at",
        "next_at",
        "display_related",
    ]
    search_fields = ["service__name", "service__slug"]
    list_filter = [
        "is_paused",
        ("consecutive_failure_count", RangeNumericFilter),
        ("last_success_at", RangeDateTimeFilter),
        ("next_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["service"]
    ordering = ["-consecutive_failure_count", "next_at"]
    actions_row = ["poll_now", "toggle_pause"]
    actions_detail = ["poll_now", "toggle_pause"]

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
                    poller__service__id__exact=obj.service_id,
                ),
                filtered_list(
                    "admin:catalog_servicecomponent_changelist",
                    _("Components"),
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
class PollRunAdmin(PollerWrittenAdmin, ModelAdmin):
    """We are the thing that tells you when services break.

    So we cannot quietly break ourselves. A failing poll is a labelled row
    here, not a number to go looking for.
    """

    # First column is plain, so it opens the run and its error text.
    list_display = [
        "poller",
        "display_service",
        "display_ok",
        "provider",
        "started_at",
        "display_error",
    ]
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

    @display(description=_("Service"), ordering="poller__service__name")
    def display_service(self, obj):
        return change_link(obj.poller.service)

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
