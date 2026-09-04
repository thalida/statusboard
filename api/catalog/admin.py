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

from catalog.models import Service, ServiceComponent, ServiceRequest, StatusPage
from catalog.queries import (
    COMPONENT_WATCHER_COUNT,
    OVERALL_SEVERITY,
    component_count,
    is_tracked,
)
from common.admin import (
    SEVERITY_VARIANTS,
    BaseModelAdmin,
    InheritedDefaultsMixin,
    ScopedAutocompleteMixin,
    ScopedAutocompleteSelect,
    audit_section,
    change_link,
    filtered_list,
    phase_label,
    severity_label,
)
from common.queries import related_count
from polling.importer import import_from_url
from polling.models import Poller, PollRun
from status.choices import EventKind, Severity
from status.models import ComponentStatus, ServiceEvent
from status.queries import CURRENT_SEVERITY


class ImportServiceForm(BaseDialogForm):
    """One field, because everything else is read from the page."""

    status_page_url = forms.URLField(
        label=_("Status page URL"),
        help_text=_("The provider is detected from it. Components and events follow."),
    )


class ComponentStatusInline(TabularInline):
    """The component's status history, read only.

    The table is append-only. A poll closes the open row and opens a
    new one, and a constraint allows exactly one open row.

    Editing it by hand rewrites history the API serves, or trips that
    constraint. So this shows the spans and changes nothing.
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

    A Poller is created by a signal, because every field has a default.
    A status page needs a URL. It is asked for here, rather than leaving
    a service that can never be polled.
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
    fields = [
        "name",
        "display_parent",
        "display_severity",
        "is_overall",
        "is_archived",
    ]
    readonly_fields = fields
    ordering = ["status_page_order", "name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(severity_now=CURRENT_SEVERITY)

    @display(description=_("Parent"))
    def display_parent(self, obj):
        # The service is the page you are on, so the path starts below it.
        return " / ".join(a.name for a in obj.ancestors) or "—"

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


class TrackedFilter(DropdownFilter):
    """Whether anybody has this service on a board.

    There is no column to filter on. `is_tracked` is the question the
    poller asks, so the admin asks it the same way.
    """

    title = _("Tracked")
    parameter_name = "tracked"

    def lookups(self, request, model_admin):
        return [("1", _("Tracked")), ("0", _("Untracked"))]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        watched = is_tracked()
        return queryset.filter(watched if self.value() == "1" else ~watched)


class ServiceSeverityFilter(DropdownFilter):
    """Filter services by the status they are actually showing.

    A service has no severity column. It is the open status of its
    overall component, the provider's own page-level reading. So this
    filters through that.
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


class ComponentSeverityFilter(DropdownFilter):
    """Filter components by the status they are showing now.

    A component has no severity column either. It is the open row of its
    status history, so this filters through that.
    """

    title = _("Status")
    parameter_name = "severity"

    def lookups(self, request, model_admin):
        return Severity.choices

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(
            statuses__ended_at__isnull=True, statuses__severity=self.value()
        )


@admin.register(Service)
class ServiceAdmin(BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin):
    list_display = [
        "display_service",
        "display_severity",
        "provider",
        "display_related",
    ]
    search_fields = [
        "name",
        "slug",
        "homepage_url",
        "status_page__url",
    ]
    # Status first: it is what anyone scanning a catalog wants.
    # What it belongs to, then what state it is in, then how much, then
    # when. A service belongs to nothing, so its state leads.
    list_filter = [
        ServiceSeverityFilter,
        ("status_page__provider", ChoicesDropdownFilter),
        TrackedFilter,
        ("created_at", RangeDateTimeFilter),
        ("updated_at", RangeDateTimeFilter),
    ]
    ordering = ["name"]
    fieldsets = [
        (None, {"fields": ["name", "slug"]}),
        (_("Presentation"), {"fields": ["logo", "homepage_url"]}),
        audit_section(),
    ]
    actions_row = ["poll_now"]
    actions_detail = ["poll_now"]
    actions_list = ["import_from_status_page"]
    # What the service is, then what is happening to it. Then how it
    # is configured, then the log of us reading it.
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
            .annotate(
                severity_now=OVERALL_SEVERITY,
                component_count=component_count(),
                event_count=related_count(ServiceEvent.objects, "service"),
                status_count=related_count(
                    ComponentStatus.objects, "component__service"
                ),
            )
        )

    @display(description=_("Service"), header=True, ordering="name")
    def display_service(self, obj):
        # Two lines and the product's own mark, so a long catalog
        # stays scannable. Unfold ignores the initials when there is an
        # image. That is the fallback the spec asks for: a missing logo
        # looks incomplete, a wrong one names the wrong product.
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
                # The count is the API's, so the admin and a client
                # never disagree about how many parts a service has.
                # The link carries the same two filters, because a
                # count beside a link describes what the link opens.
                # Clearing a chip reaches the rollup and the archive.
                filtered_list(
                    "admin:catalog_servicecomponent_changelist",
                    _("Components"),
                    obj.component_count,
                    service__id__exact=obj.pk,
                    is_overall__exact=0,
                    is_archived__exact=0,
                ),
                filtered_list(
                    "admin:status_serviceevent_changelist",
                    _("Events"),
                    obj.event_count,
                    service__id__exact=obj.pk,
                ),
                filtered_list(
                    "admin:status_componentstatus_changelist",
                    _("Status history"),
                    obj.status_count,
                    component__service__id__exact=obj.pk,
                ),
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


# StatusPage has no admin of its own. A service has exactly one, edited
# on the service form. A separate list would be a second route to the
# same field. The model still filters the service list by provider.


@admin.register(ServiceComponent)
class ServiceComponentAdmin(
    ScopedAutocompleteMixin, BaseModelAdmin, SimpleHistoryAdmin, ModelAdmin
):
    list_display = [
        "display_component",
        "display_service",
        "display_severity",
        "is_overall",
        "display_archived",
        "display_related",
        "watchers",
        # `suggested` reads this flag on every component. Ticking it on
        # a rollup surfaces the service. Ticking it on a leaf surfaces
        # that part.
        "is_featured",
    ]
    search_fields = [
        "name",
        "external_id",
        "parent__name",
        "service__name",
        "service__slug",
    ]
    # Service first: it is how anyone narrows a list of every component
    # of every service.
    list_filter = [
        ("service", AutocompleteSelectFilter),
        ("parent", AutocompleteSelectFilter),
        ComponentSeverityFilter,
        "is_overall",
        ("status_page_order", RangeNumericFilter),
        "is_archived",
        ("archived_at", RangeDateTimeFilter),
        ("created_at", RangeDateTimeFilter),
        "is_featured",
    ]
    autocomplete_fields = ["service", "parent"]
    ordering = ["service__name", "status_page_order"]
    # A parent is one of the same service's components.
    autocomplete_scope = ("service",)
    # The date follows the flag, so it is shown and never typed.
    readonly_fields = ["archived_at"]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "service",
                    "name",
                    "external_id",
                    "is_archived",
                    "archived_at",
                ]
            },
        ),
        (
            _("Position"),
            {"fields": ["parent", "status_page_order", "is_overall"]},
        ),
        (
            _("Featuring"),
            {
                "fields": ["is_featured"],
                "description": _(
                    "Leads the suggested sort on the catalog. Tick it on any "
                    "component. A rollup surfaces its service, and a leaf "
                    "surfaces that part."
                ),
            },
        ),
        audit_section(),
    ]
    inlines = [ComponentStatusInline]
    # Two, not a toggle. A selection can mix already-featured and not,
    # and a toggle would leave an admin unable to predict the result.
    # `PollerAdmin.toggle_pause` can be one action because it only ever
    # acts on a single object, which has one state to flip.
    actions = ["feature_selected", "unfeature_selected"]

    def get_form(self, request, obj=None, **kwargs):
        # The parent picker needs to know which service is asking.
        request._editing = obj
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            editing = getattr(request, "_editing", None)
            kwargs["widget"] = ScopedAutocompleteSelect(
                db_field,
                self.admin_site,
                scope={"service": editing.service_id if editing else None},
            )
            # The rollup is never a parent. Excluding it here, on both
            # add and change, keeps the picker from offering the one
            # choice the database refuses.
            queryset = ServiceComponent.objects.exclude(is_overall=True)
            if editing is not None:
                # The server's half: the picker narrows what is offered,
                # this refuses anything else that is posted.
                queryset = queryset.filter(service_id=editing.service_id).exclude(
                    pk=editing.pk
                )
            kwargs["queryset"] = queryset
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("service", "parent")
            .annotate(
                severity_now=CURRENT_SEVERITY,
                status_count=related_count(ComponentStatus.objects, "component"),
                event_count=related_count(ServiceEvent.objects, "affected_components"),
                watcher_count=COMPONENT_WATCHER_COUNT,
            )
        )

    @display(description=_("Component"), header=True, ordering="name")
    def display_component(self, obj):
        # The second line is where the component sits, not the
        # provider's key. The key is on the record for anyone who needs
        # it, and says nothing to a reader scanning a list.
        return [
            obj.name,
            " / ".join([obj.service.name, *(a.name for a in obj.ancestors)]),
        ]

    @display(description=_("Service"), ordering="service__name")
    def display_service(self, obj):
        return change_link(obj.service)

    @display(
        description=_("State"),
        label={"Live": "success", "Archived": "default"},
        ordering="is_archived",
    )
    def display_archived(self, obj):
        # An archived component still reads on the table. Without this
        # it looked like one the provider is still publishing.
        return "Archived" if obj.is_archived else "Live"

    @display(description=_("View"), dropdown=True)
    def display_related(self, obj):
        return {
            "title": _("Related"),
            "items": [
                filtered_list(
                    "admin:status_componentstatus_changelist",
                    _("Status history"),
                    obj.status_count,
                    component__id__exact=obj.pk,
                ),
                filtered_list(
                    "admin:status_serviceevent_changelist",
                    _("Events"),
                    obj.event_count,
                    affected_components__id__exact=obj.pk,
                ),
            ],
        }

    @display(description=_("Status"), label=SEVERITY_VARIANTS, ordering="severity_now")
    def display_severity(self, obj):
        return severity_label(obj.severity_now)

    @display(description=_("Watchers"), ordering="watcher_count")
    def watchers(self, obj):
        return obj.watcher_count

    @admin.action(description=_("Feature selected components"))
    def feature_selected(self, request, queryset):
        """Feature every selected component, rollup or leaf.

        The change form above sets the same flag one row at a time.
        Both are unrestricted, because `suggested` reads the flag on
        every component and a featured leaf is a real editorial choice.
        """
        count = 0
        for component in queryset.filter(is_featured=False):
            component.is_featured = True
            component.save(update_fields=["is_featured"])
            count += 1
        self.message_user(
            request, _("Featured %(count)d component(s).") % {"count": count}
        )

    @admin.action(description=_("Unfeature selected components"))
    def unfeature_selected(self, request, queryset):
        count = 0
        for component in queryset.filter(is_featured=True):
            component.is_featured = False
            component.save(update_fields=["is_featured"])
            count += 1
        self.message_user(
            request, _("Unfeatured %(count)d component(s).") % {"count": count}
        )


@admin.register(ServiceRequest)
class ServiceRequestAdmin(ModelAdmin):
    """What the catalog is missing, most asked for first."""

    list_display = ["url", "request_count", "last_requested_at", "created_by"]
    ordering = ["-request_count", "-last_requested_at"]
    search_fields = ["url"]
    readonly_fields = ["url", "request_count", "last_requested_at"]

    def has_add_permission(self, request):
        # A row arrives from the app, never from here.
        return False
