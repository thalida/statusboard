from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    DropdownFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
)
from unfold.contrib.inlines.admin import NonrelatedTabularInline
from unfold.dataclasses import ActionDialog
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import BaseDialogForm

from catalog.models import Service, ServiceComponent, StatusPage
from common.admin import (
    SEVERITY_VARIANTS,
    BaseModelAdmin,
    InheritedDefaultsMixin,
    change_link,
    filtered_list,
    phase_label,
    severity_label,
)
from common.ordering import CURRENT_SEVERITY, OVERALL_SEVERITY
from polling.models import Poller, PollRun
from status.choices import EventKind, Severity
from status.models import ComponentStatus, ServiceEvent


class ImportServiceForm(BaseDialogForm):
    """One field, because everything else is read from the page."""

    status_page_url = forms.URLField(
        label=_("Status page URL"),
        help_text=_("The provider is detected from it. Components and events follow."),
    )


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
    # Read only, but still worth opening: the row is a summary.
    show_change_link = True
    per_page = 10
    fields = ["display_severity", "source", "started_at", "ended_at"]
    readonly_fields = fields
    ordering = ["-started_at"]

    @display(description=_("Severity"), label=SEVERITY_VARIANTS)
    def display_severity(self, obj):
        return severity_label(obj.severity)

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
    verbose_name = _("Status page")
    verbose_name_plural = _("Status page")
    extra = 1
    max_num = 1
    can_delete = False


class PollerInline(InheritedDefaultsMixin, StackedInline):
    """How often this service is polled, and how that is going.

    Editable, unlike the records a poll writes. The interval, the
    cooldown and the pause flag are meant to be tuned here.
    """

    model = Poller
    tab = True
    verbose_name = _("Polling")
    verbose_name_plural = _("Polling")
    extra = 0
    max_num = 1
    can_delete = False
    show_change_link = True
    fields = [
        "is_paused",
        "interval_seconds",
        "cooldown_seconds",
        "max_interval_seconds",
        "note",
        "consecutive_failure_count",
        "last_success_at",
        "next_at",
    ]
    readonly_fields = ["consecutive_failure_count", "last_success_at", "next_at"]

    def has_add_permission(self, request, obj=None):
        # A signal makes it with the service. There is never a second one.
        return False


class PollRunInline(NonrelatedTabularInline):
    """The service's recent polls, read only.

    A PollRun points at a Poller, not at a Service, so this cannot be an
    ordinary inline. The rows still belong here: a stale reading is
    explained by the run that produced it.
    """

    model = PollRun
    tab = True
    verbose_name = _("Poll run")
    verbose_name_plural = _("Poll runs")
    extra = 0
    can_delete = False
    show_change_link = True
    per_page = 10
    fields = ["started_at", "ok", "provider", "error"]
    readonly_fields = fields
    ordering = ["-started_at"]

    def get_form_queryset(self, service):
        return PollRun.objects.filter(poller__service=service).order_by("-started_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ServiceComponentInline(TabularInline):
    """The service's components, read only.

    A poll upserts these from the provider, keyed on external_id. This is
    a summary; the change link opens the full record.
    """

    model = ServiceComponent
    tab = True
    verbose_name = _("Component")
    verbose_name_plural = _("Components")
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True
    per_page = 20
    fields = ["name", "external_id", "display_severity", "is_overall", "archived_at"]
    readonly_fields = fields
    ordering = ["status_page_order", "name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(severity_now=CURRENT_SEVERITY)

    @display(description=_("Status"), label=SEVERITY_VARIANTS)
    def display_severity(self, obj):
        return severity_label(obj.severity_now)

    def has_add_permission(self, request, obj=None):
        return False


class ServiceEventInline(TabularInline):
    """The service's incidents and maintenance, read only.

    A poll upserts these from the provider. Editing one here would make
    the admin disagree with the status page it mirrors.
    """

    model = ServiceEvent
    tab = True
    verbose_name = _("Event")
    verbose_name_plural = _("Events")
    extra = 0
    max_num = 0
    can_delete = False
    # Read only, but still worth opening: the row is a summary.
    show_change_link = True
    per_page = 10
    fields = ["display_kind", "title", "display_phase", "starts_at", "ends_at"]
    readonly_fields = fields
    ordering = ["-starts_at"]

    @display(
        description=_("Kind"),
        label={
            EventKind.INCIDENT.label: "danger",
            EventKind.MAINTENANCE.label: "info",
        },
    )
    def display_kind(self, obj):
        return EventKind(obj.kind).label

    @display(description=_("Phase"), label=True)
    def display_phase(self, obj):
        return phase_label(obj)

    def has_add_permission(self, request, obj=None):
        return False


class ServiceSeverityFilter(DropdownFilter):
    """Filter services by the status they are actually showing.

    A service has no severity column. It is the open status of its
    overall component, which is the provider's own page-level reading,
    so this filters through that rather than on the service.
    """

    title = _("Status")
    parameter_name = "severity"

    def lookups(self, request, model_admin):
        return Severity.choices

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(
            components__is_overall=True,
            components__statuses__ended_at__isnull=True,
            components__statuses__severity=self.value(),
        )


@admin.register(Service)
class ServiceAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = [
        "display_service",
        "display_severity",
        "watcher_count",
        "provider",
        "display_related",
    ]
    search_fields = ["name", "slug", "homepage_url"]
    # Status first: it is what anyone scanning a catalog wants.
    list_filter = [
        ServiceSeverityFilter,
        "is_featured",
        ("status_page__provider", ChoicesDropdownFilter),
        ("watcher_count", RangeNumericFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    ordering = ["-watcher_count", "name"]
    actions_row = ["poll_now"]
    actions_detail = ["poll_now"]
    actions_list = ["import_from_status_page"]
    # What the service is, then what is happening to it, then how it is
    # configured, then the log of us reading it.
    inlines = [
        ServiceComponentInline,
        ServiceEventInline,
        StatusPageInline,
        PollerInline,
        PollRunInline,
    ]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("status_page", "poller")
            .annotate(severity_now=OVERALL_SEVERITY)
        )

    @display(description=_("Service"), header=True, ordering="name")
    def display_service(self, obj):
        # Two lines and the product's own mark, so a long catalog stays
        # scannable. Unfold ignores the initials when there is an image,
        # which is the fallback the spec asks for: a missing logo looks
        # incomplete, a wrong one names the wrong product.
        return [
            obj.name,
            obj.slug,
            obj.name[:2].upper(),
            {"path": obj.logo, "squared": False, "borderless": True},
        ]

    @display(description=_("Status"), label=SEVERITY_VARIANTS, ordering="severity_now")
    def display_severity(self, obj):
        return severity_label(obj.severity_now)

    @display(description=_("Provider"))
    def provider(self, obj):
        page = getattr(obj, "status_page", None)
        return page.get_provider_display() if page else "—"

    @display(description=_("View"), dropdown=True)
    def display_related(self, obj):
        """Everything hanging off this service, one filtered list each.

        Reaching a service's components meant opening their changelist and
        filtering it by hand.
        """
        return {
            "title": _("Related"),
            "items": [
                {
                    "title": _("Components"),
                    "link": (
                        reverse("admin:catalog_servicecomponent_changelist")
                        + f"?service__id__exact={obj.pk}"
                    ),
                },
                {
                    "title": _("Events"),
                    "link": (
                        reverse("admin:status_serviceevent_changelist")
                        + f"?service__id__exact={obj.pk}"
                    ),
                },
                {
                    "title": _("Status history"),
                    "link": (
                        reverse("admin:status_componentstatus_changelist")
                        + f"?component__service__id__exact={obj.pk}"
                    ),
                },
                {
                    "title": _("Poll runs"),
                    "link": (
                        reverse("admin:polling_pollrun_changelist")
                        + f"?poller__service__id__exact={obj.pk}"
                    ),
                },
            ],
        }

    @action(
        description=_("Import from URL"),
        icon="cloud_download",
        url_path="import-from-url",
        variant=ActionVariant.PRIMARY,
        permissions=["poll_now"],
        dialog=ActionDialog(
            title=_("Import a service"),
            description=_(
                "Paste a status page. The name, components and event history "
                "are read from it, and polling starts on the next tick."
            ),
            form_class=ImportServiceForm,
            form_submit_text=_("Import"),
        ),
    )
    def import_from_status_page(self, request, form):
        if not form.is_valid():
            self.message_user(request, _("Enter a valid URL."), level="error")
            return redirect(reverse("admin:catalog_service_changelist"))

        url = form.cleaned_data["status_page_url"]
        try:
            service, created = Service.objects.import_from_url(url)
        except Exception as error:  # noqa: BLE001 — the page is a stranger's
            # Anything can come back from a URL a person pasted. Say what
            # happened rather than showing a 500.
            self.message_user(
                request, f"{url} could not be read: {error}", level="error"
            )
            return redirect(reverse("admin:catalog_service_changelist"))

        self.message_user(
            request,
            _("Imported %(name)s.") % {"name": service.name}
            if created
            else _("%(name)s was already in the catalog.") % {"name": service.name},
        )
        return redirect(reverse("admin:catalog_service_change", args=[service.pk]))

    @action(
        description=_("Poll now"),
        icon="sync",
        url_path="poll-now",
        variant=ActionVariant.PRIMARY,
        permissions=["poll_now"],
    )
    def poll_now(self, request, object_id):
        from polling.tasks import poll_service

        poll_service.delay(str(object_id))
        self.message_user(request, _("Queued a poll for this service."))

    def has_poll_now_permission(self, request, obj=None):
        return request.user.has_perm("catalog.change_service")


# StatusPage has no admin of its own. A service has exactly one and it is
# edited on the service form, so a separate list is a second route to the
# same field. The model still filters the service list by provider.


@admin.register(ServiceComponent)
class ServiceComponentAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = [
        "display_component",
        "display_service",
        "display_severity",
        "is_overall",
        "display_related",
    ]
    search_fields = ["name", "external_id", "service__name"]
    # Service first: it is how anyone narrows a list of every component
    # of every service.
    list_filter = [
        ("service", AutocompleteSelectFilter),
        "is_overall",
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
        return [obj.name, obj.external_id]

    @display(description=_("Service"), ordering="service__name")
    def display_service(self, obj):
        return change_link(obj.service)

    @display(description=_("View"), dropdown=True)
    def display_related(self, obj):
        return {
            "title": _("Related"),
            "items": [
                filtered_list(
                    "admin:status_componentstatus_changelist",
                    _("Status history"),
                    component__id__exact=obj.pk,
                ),
                filtered_list(
                    "admin:status_serviceevent_changelist",
                    _("Events"),
                    affected_components__id__exact=obj.pk,
                ),
            ],
        }

    @display(description=_("Status"), label=SEVERITY_VARIANTS, ordering="severity_now")
    def display_severity(self, obj):
        return severity_label(obj.severity_now)
