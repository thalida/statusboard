from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesDropdownFilter,
    DropdownFilter,
    RangeDateTimeFilter,
)
from unfold.decorators import display

from catalog.models import ServiceComponent
from common.admin import (
    SEVERITY_VARIANTS,
    PollerWrittenAdmin,
    audit_section,
    change_link,
    date_span,
    filtered_list,
    phase_label,
    poll_run_link,
    record_column,
    related_count,
    severity_label,
)
from status.choices import CLOSED_PHASES, EVENT_PHASES_BY_KIND, EventKind
from status.models import ComponentStatus, EventUpdate, ServiceEvent


class PhaseFilter(DropdownFilter):
    """Phase is a plain column, so its options are assembled here.

    An incident and a maintenance window move through different phases,
    which is why the field carries no choices of its own.
    """

    title = _("Phase")
    parameter_name = "phase"

    def lookups(self, request, model_admin):
        return [
            (phase.value, f"{kind.label}: {phase.label}")
            for kind, phases in EVENT_PHASES_BY_KIND.items()
            for phase in phases
        ]

    def queryset(self, request, queryset):
        return queryset.filter(phase=self.value()) if self.value() else queryset


@admin.register(ComponentStatus)
class ComponentStatusAdmin(PollerWrittenAdmin, ModelAdmin):
    list_display = [
        "display_reading",
        "display_component",
        "display_service",
        "display_severity",
        "display_span",
        "display_source",
        "display_poll_run",
    ]
    date_hierarchy = "started_at"
    search_fields = [
        "component__name",
        "component__external_id",
        "component__service__name",
        "component__service__slug",
    ]
    # Also what makes ?component__service__id__exact and
    # ?poll_run__id__exact permitted lookups, which is how the services
    # table and a poll run reach the readings they own.
    list_filter = [
        ("component__service", AutocompleteSelectFilter),
        ("component", AutocompleteSelectFilter),
        ("poll_run", AutocompleteSelectFilter),
        ("severity", ChoicesDropdownFilter),
        ("source", ChoicesDropdownFilter),
        ("started_at", RangeDateTimeFilter),
        ("ended_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["component"]
    ordering = ["-started_at"]
    fieldsets = [
        (None, {"fields": ["component", "severity", "source"]}),
        (_("Span"), {"fields": ["started_at", "ended_at"]}),
        (_("Written by"), {"fields": ["display_poll_run"]}),
        audit_section(),
    ]
    display_reading = record_column(_("Reading"))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("component__service")

    @display(description=_("Component"), ordering="component__name")
    def display_component(self, obj):
        return change_link(obj.component)

    @display(description=_("Span"), ordering="started_at")
    def display_span(self, obj):
        # A row is a stretch, and the open one is the reading now. With
        # the start alone there was no telling which rows were still
        # standing.
        return date_span(obj.started_at, obj.ended_at)

    @display(description=_("Source"))
    def display_source(self, obj):
        # How the severity was arrived at, which is not the same question
        # as what it is.
        return obj.get_source_display()

    def get_readonly_fields(self, request, obj=None):
        # The run is not an editable column, so it reaches the record
        # only this way. Without it you could see where a reading came
        # from on the table and not on the reading itself.
        fields = list(super().get_readonly_fields(request, obj))
        return fields + ["display_poll_run"]

    @display(description=_("Severity"), label=SEVERITY_VARIANTS, ordering="severity")
    def display_severity(self, obj):
        return severity_label(obj.severity)

    @display(description=_("Written by"))
    def display_poll_run(self, obj):
        return poll_run_link(obj)

    @display(description=_("Service"), ordering="component__service__name")
    def display_service(self, obj):
        return change_link(obj.component.service)


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
    # Read only, but still worth opening: the row is a summary.
    show_change_link = True
    per_page = 10
    fields = ["phase", "body", "posted_at"]
    readonly_fields = fields
    ordering = ["-posted_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceEvent)
class ServiceEventAdmin(PollerWrittenAdmin, ModelAdmin):
    list_display = [
        "title",
        "display_service",
        "display_when",
        "display_kind",
        "display_phase",
        "display_related",
    ]
    date_hierarchy = "starts_at"
    search_fields = ["title", "external_id", "service__name", "service__slug"]
    # Also what makes ?poll_run__id__exact a permitted lookup, which is
    # how a run reaches the events it wrote.
    list_filter = [
        ("service", AutocompleteSelectFilter),
        ("affected_components", AutocompleteSelectFilter),
        ("poll_run", AutocompleteSelectFilter),
        ("kind", ChoicesDropdownFilter),
        PhaseFilter,
        ("starts_at", RangeDateTimeFilter),
        ("ends_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["service"]
    filter_horizontal = ["affected_components"]

    def get_form(self, request, obj=None, **kwargs):
        # The component picker needs to know whose event this is.
        request._editing = obj
        return super().get_form(request, obj, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "affected_components":
            editing = getattr(request, "_editing", None)
            if editing is not None:
                # An event names its own service's components. Offering
                # the rest lets one product's incident claim another
                # product's parts.
                kwargs["queryset"] = ServiceComponent.objects.filter(
                    service_id=editing.service_id
                )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_related(self, request, form, formsets, change):
        """Refuse a component of another service.

        The relation is set after the row is saved, so the model's own
        `clean` never sees it. This is the last point that can.
        """
        super().save_related(request, form, formsets, change)
        strays = form.instance.components_of_another_service()
        if strays.exists():
            names = ", ".join(str(c) for c in strays)
            form.instance.affected_components.remove(*strays)
            self.message_user(
                request,
                _("Removed %s. An event names its own service's components.") % names,
                messages.WARNING,
            )

    ordering = ["-starts_at"]
    inlines = [EventUpdateInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("service")
            .annotate(
                update_count=related_count(EventUpdate.objects, "event"),
                component_count=related_count(
                    ServiceComponent.objects, "service", ref="service_id"
                ),
            )
        )

    @display(description=_("When"), ordering="starts_at")
    def display_when(self, obj):
        return date_span(obj.starts_at, obj.ends_at)

    def get_fieldsets(self, request, obj=None):
        # Editable, the components need their picker. Read only, they are
        # more useful as links than as a comma-separated string.
        components = (
            "affected_components"
            if self.has_change_permission(request, obj)
            else "display_affected_components"
        )
        return [
            (None, {"fields": ["service", "external_id", "title"]}),
            (_("What kind"), {"fields": ["kind", "phase"]}),
            (_("When"), {"fields": ["starts_at", "ends_at"]}),
            (_("Affected"), {"fields": [components]}),
            (_("Written by"), {"fields": ["display_poll_run"]}),
            audit_section(),
        ]

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        return fields + ["display_affected_components", "display_poll_run"]

    @display(description=_("Service"), ordering="service__name")
    def display_service(self, obj):
        return change_link(obj.service)

    @display(description=_("View"), dropdown=True)
    def display_related(self, obj):
        return {
            "title": _("Related"),
            "items": [
                filtered_list(
                    "admin:status_eventupdate_changelist",
                    _("Updates"),
                    obj.update_count,
                    event__id__exact=obj.pk,
                ),
                filtered_list(
                    "admin:catalog_servicecomponent_changelist",
                    _("Components"),
                    obj.component_count,
                    service__id__exact=obj.service_id,
                ),
            ],
        }

    @display(description=_("Written by"))
    def display_poll_run(self, obj):
        return poll_run_link(obj)

    @display(description=_("Affected components"))
    def display_affected_components(self, obj):
        rows = obj.affected_components.select_related("service")
        if not rows:
            return "—"
        return format_html_join(
            mark_safe(", "),
            '<a href="{}" class="text-primary-600 dark:text-primary-500">{}</a>',
            (
                (
                    reverse(
                        "admin:catalog_servicecomponent_change", args=[component.pk]
                    ),
                    component.name,
                )
                for component in rows
            ),
        )

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
        return phase_label(obj)

    @display(description=_("Open"), boolean=True)
    def display_open(self, obj):
        return obj.phase not in CLOSED_PHASES


@admin.register(EventUpdate)
class EventUpdateAdmin(PollerWrittenAdmin, ModelAdmin):
    list_display = [
        "display_update",
        "display_event",
        "display_service",
        "phase",
        "posted_at",
    ]
    display_update = record_column(_("Update"))
    date_hierarchy = "posted_at"
    search_fields = [
        "event__title",
        "event__external_id",
        "event__service__name",
        "body",
    ]
    autocomplete_fields = ["event"]
    list_filter = [
        ("event__service", AutocompleteSelectFilter),
        ("event", AutocompleteSelectFilter),
        ("posted_at", RangeDateTimeFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    fieldsets = [
        (None, {"fields": ["event", "phase", "posted_at"]}),
        (_("What was posted"), {"fields": ["body"]}),
        audit_section(),
    ]

    @display(description=_("Service"), ordering="event__service__name")
    def display_service(self, obj):
        return change_link(obj.event.service)

    @display(description=_("Event"), ordering="event__title")
    def display_event(self, obj):
        return change_link(obj.event, obj.event.title)
