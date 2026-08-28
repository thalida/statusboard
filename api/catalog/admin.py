from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
)
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from catalog.models import Poller, Service, ServiceComponent, StatusPage
from common.admin import BaseModelAdmin
from common.ordering import CURRENT_SEVERITY
from status.choices import Severity
from status.models import ComponentStatus, ServiceEvent

# Lower is worse, so the scale runs danger to success.
SEVERITY_VARIANTS = {
    Severity.MAJOR_OUTAGE.label: "danger",
    Severity.PARTIAL_OUTAGE.label: "danger",
    Severity.DEGRADED.label: "warning",
    Severity.UNKNOWN.label: "default",
    Severity.MAINTENANCE.label: "info",
    Severity.OPERATIONAL.label: "success",
}


def _severity_label(value):
    return Severity(value).label if value is not None else "—"


class ComponentStatusInline(TabularInline):
    """The component's status history, read only.

    The table is append-only: a poll closes the open row and opens a new
    one, and a partial unique constraint allows exactly one open row. Hand
    editing it would either rewrite history the API serves or trip that
    constraint, so this shows the spans and offers no way to change them.
    """

    model = ComponentStatus
    tab = True
    extra = 0
    max_num = 0
    can_delete = False
    per_page = 10
    fields = ["severity", "source", "started_at", "ended_at"]
    readonly_fields = fields
    ordering = ["-started_at"]

    def has_add_permission(self, request, obj=None):
        return False


class StatusPageInline(StackedInline):
    """The one thing a service cannot be given automatically.

    A Poller is created by a signal because every field has a default. A
    status page needs a URL, so it is asked for here instead of leaving a
    service that can never be polled.
    """

    model = StatusPage
    tab = True
    extra = 1
    max_num = 1
    can_delete = False


class ServiceEventInline(TabularInline):
    """The service's incidents and maintenance, read only.

    A poll upserts these from the provider. Editing one here would make
    the admin disagree with the status page it mirrors.
    """

    model = ServiceEvent
    tab = True
    extra = 0
    max_num = 0
    can_delete = False
    per_page = 10
    fields = ["kind", "title", "phase", "starts_at", "ends_at"]
    readonly_fields = fields
    ordering = ["-starts_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Service)
class ServiceAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = ["display_service", "display_severity", "watcher_count", "provider"]
    search_fields = ["name", "slug", "homepage_url"]
    list_filter = [
        "is_featured",
        ("status_page__provider", ChoicesDropdownFilter),
        ("watcher_count", RangeNumericFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    ordering = ["-watcher_count", "name"]
    actions_row = ["poll_now"]
    actions_detail = ["poll_now"]
    inlines = [StatusPageInline, ServiceEventInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("status_page", "poller")

    @display(description=_("Service"), header=True, ordering="name")
    def display_service(self, obj):
        # Two lines and an avatar initial, so a long catalog stays scannable.
        return [obj.name, obj.slug, obj.name[:2].upper()]

    @display(description=_("Status"), label=SEVERITY_VARIANTS)
    def display_severity(self, obj):
        row = (
            obj.components.filter(is_overall=True)
            .values_list("statuses__severity", flat=True)
            .filter(statuses__ended_at__isnull=True)
            .first()
        )
        return _severity_label(row)

    @display(description=_("Provider"))
    def provider(self, obj):
        page = getattr(obj, "status_page", None)
        return page.get_provider_display() if page else "—"

    @action(
        description=_("Poll now"),
        icon="sync",
        url_path="poll-now",
        variant=ActionVariant.PRIMARY,
        permissions=["poll_now"],
    )
    def poll_now(self, request, object_id):
        from status.tasks import poll_service

        poll_service.delay(str(object_id))
        self.message_user(request, _("Queued a poll for this service."))

    def has_poll_now_permission(self, request, obj=None):
        return request.user.has_perm("catalog.change_service")


@admin.register(StatusPage)
class StatusPageAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = ["service", "display_provider", "url"]
    search_fields = ["service__name", "url"]
    list_filter = [("provider", ChoicesDropdownFilter)]
    autocomplete_fields = ["service"]

    @display(description=_("Provider"), label=True, ordering="provider")
    def display_provider(self, obj):
        return obj.get_provider_display()


@admin.register(Poller)
class PollerAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    """Where a stalled poller is supposed to be obvious.

    A service that stops being polled shows every board a stale green,
    which is worse than showing nothing.
    """

    list_display = [
        "service",
        "display_health",
        "consecutive_failure_count",
        "last_success_at",
        "next_at",
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
        from status.tasks import poll_service

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


@admin.register(ServiceComponent)
class ServiceComponentAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = [
        "display_component",
        "display_severity",
        "is_overall",
        "archived_at",
    ]
    search_fields = ["name", "external_id", "service__name"]
    list_filter = [
        "is_overall",
        ("service", AutocompleteSelectFilter),
        ("archived_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["service", "parent"]
    ordering = ["service__name", "status_page_order"]
    inlines = [ComponentStatusInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("service", "parent")
            .annotate(severity_now=CURRENT_SEVERITY)
        )

    @display(description=_("Component"), header=True, ordering="name")
    def display_component(self, obj):
        return [obj.name, obj.service.name]

    @display(description=_("Status"), label=SEVERITY_VARIANTS, ordering="severity_now")
    def display_severity(self, obj):
        return _severity_label(obj.severity_now)
