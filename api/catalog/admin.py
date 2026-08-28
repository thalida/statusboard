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
    RangeDateTimeFilter,
    RangeNumericFilter,
)
from unfold.dataclasses import ActionDialog
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import BaseDialogForm

from catalog.import_service import import_from_url
from catalog.models import Service, ServiceComponent, StatusPage
from common.admin import SEVERITY_VARIANTS, BaseModelAdmin, severity_label
from common.ordering import CURRENT_SEVERITY
from status.choices import EventKind
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
        return obj.phase.replace("_", " ").title()

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
    actions_list = ["import_from_status_page"]
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
        return severity_label(row)

    @display(description=_("Provider"))
    def provider(self, obj):
        page = getattr(obj, "status_page", None)
        return page.get_provider_display() if page else "—"

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
            service, created = import_from_url(url)
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


@admin.register(StatusPage)
class StatusPageAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = ["service", "display_provider", "url"]
    search_fields = ["service__name", "url"]
    list_filter = [("provider", ChoicesDropdownFilter)]
    autocomplete_fields = ["service"]

    @display(description=_("Provider"), label=True, ordering="provider")
    def display_provider(self, obj):
        return obj.get_provider_display()


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
        return severity_label(obj.severity_now)
