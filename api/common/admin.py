"""Admin-wide callbacks: the environment badge and the dashboard."""

import json
from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings
from django.contrib.admin.widgets import AutocompleteSelect
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, TruncHour
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from api.defaults import Environment
from status.choices import EVENT_PHASES_BY_KIND, Severity


def environment_callback(request):
    """Colour the banner by database.

    Acting on production while believing it is development is the mistake
    worth making loud.
    """
    # `default` is the neutral label. Development is not a warning, and a
    # blue badge would read as the maintenance colour. Settings validates
    # the variable, so there is no unknown value to fall back for.
    return {
        Environment.DEVELOPMENT: ["Development", "default"],
        Environment.STAGING: ["Staging", "warning"],
        Environment.PRODUCTION: ["Production", "danger"],
    }[settings.ENVIRONMENT]


def environment_prefix_callback(request):
    """Put the environment in the browser tab, where a stray tab shows it."""
    if settings.ENVIRONMENT is Environment.PRODUCTION:
        return ""
    return f"[{settings.ENVIRONMENT}]"


def dashboard_callback(request, context):
    """Answer one question: is polling healthy?

    We are the thing that tells you when services break. A stalled
    poller shows every board a stale green. That is worse than showing
    nothing, so this page leads with the poller.
    """
    from catalog.models import Service
    from polling.models import Poller, PollRun
    from polling.tasks import active_pollers

    now = timezone.now()
    day_ago = now - timezone.timedelta(hours=24)

    # Not every Poller row is run. An untracked service is never
    # dispatched, nor is one with no status page. So neither can be late
    # or stale. `active_pollers` is the scheduler's own definition.
    late_after = now - timezone.timedelta(seconds=settings.POLL_COOLDOWN_SECONDS)
    active = active_pollers()
    pollers = {
        "failing": active.filter(consecutive_failure_count__gt=0).count(),
        "paused": Poller.objects.filter(is_paused=True).count(),
        "late": active.filter(
            Q(next_at__isnull=True) | Q(next_at__lt=late_after)
        ).count(),
    }
    stalest = _stalest_card(active, now)
    runs = PollRun.objects.filter(started_at__gte=day_ago).aggregate(
        total=Count("id"), failed=Count("id", filter=Q(ok=False))
    )
    succeeded = runs["total"] - runs["failed"]
    ok_rate = round(100 * succeeded / runs["total"]) if runs["total"] else None

    context["cards"] = [
        {
            "title": "Services tracked",
            "value": Service.objects.filter(watcher_count__gt=0).count(),
            "icon": "lan",
            "detail": f"{Service.objects.count()} in the catalog",
        },
        {
            # Backoff was the headline and overdue the footnote. So
            # the card read 0 while a poller had stopped. Both answer
            # one question, and late is the worse answer.
            #
            # Late means past due by more than a cooldown. A poller
            # waiting on the next beat is not an alarm.
            "title": "Behind schedule",
            "value": pollers["late"],
            "icon": "schedule_send",
            "danger": pollers["late"] > 0,
            "detail": (f"{pollers['failing']} in backoff, {pollers['paused']} paused"),
        },
        {
            "title": "Poll success, 24h",
            "value": "—" if ok_rate is None else f"{ok_rate}%",
            "icon": "check_circle",
            "danger": ok_rate is not None and ok_rate < 95,
            # "22 runs, 21 failed" beside "5%" reads as a contradiction.
            # Say the number the percentage is of.
            "detail": f"{succeeded} of {runs['total']} runs succeeded",
        },
        stalest,
    ]
    context["poll_chart"] = _hourly_chart(day_ago, now)
    context["poll_chart_options"] = POLL_CHART_OPTIONS
    context["tracking_chart"] = _tracking_chart(now)
    context["tracking_chart_options"] = TRACKING_CHART_OPTIONS
    context["failure_causes"] = _failure_causes(day_ago)
    context["failed_runs_link"] = (
        f"{reverse('admin:polling_pollrun_changelist')}?ok__exact=0"
    )
    return context


CHART_OK = "#59CE87"
CHART_FAILED = "#F27967"
CHART_TRACKED = "#66B5EC"


def _stalest_card(active, now):
    """The tracked service whose data is oldest, named.

    A `min()` across every poller moved only when the worst recovered.
    It did not say which one that was. It also counted services nobody
    tracks, which are stale because nothing polls them.
    """
    worst = (
        active.select_related("service")
        .order_by(F("last_success_at").asc(nulls_first=True))
        .first()
    )
    return {
        "title": "Stalest service",
        "value": "—" if worst is None else _ago(worst.last_success_at, now),
        "icon": "schedule",
        "danger": worst is not None and worst.last_success_at is None,
        "detail": "Nothing tracked" if worst is None else str(worst.service),
    }


def _tracking_chart(now):
    """Thirty days of the board filling up.

    Nothing records untracking, so the line is the currently tracked set
    placed on the day each service joined it.
    """
    from dashboards.models import DashboardItem

    started = {}
    for service_id, when in DashboardItem.objects.filter(
        component__service__watcher_count__gt=0
    ).values_list("component__service_id", "created_at"):
        day = localtime(when).date()
        if service_id not in started or day < started[service_id]:
            started[service_id] = day
    today = localtime(now).date()
    days = [today - timezone.timedelta(days=n) for n in range(29, -1, -1)]
    joined = sorted(started.values())
    return json.dumps(
        {
            "labels": [d.strftime("%-d %b") for d in days],
            "datasets": [
                {
                    "label": "Tracked",
                    "data": [sum(1 for j in joined if j <= d) for d in days],
                    "borderColor": CHART_TRACKED,
                    "backgroundColor": CHART_TRACKED,
                    "fill": False,
                }
            ],
        }
    )


TRACKING_CHART_OPTIONS = json.dumps(
    {
        "animation": False,
        "responsive": True,
        "maintainAspectRatio": False,
        "scales": {
            "x": {"grid": {"display": False}},
            "y": {"beginAtZero": True, "ticks": {"precision": 0}},
        },
        "plugins": {"legend": {"display": False}},
    }
)


def _hourly_chart(day_ago, now):
    """Twenty-four hours of polling, stacked ok over failed, one bar an hour."""
    from polling.models import PollRun

    counted = {
        row["hour"]: row
        for row in PollRun.objects.filter(started_at__gte=day_ago)
        .annotate(hour=TruncHour("started_at"))
        .values("hour")
        # Not `ok`: an annotation named after the field it filters on
        # makes the filter refer to itself.
        .annotate(
            ok_count=Count("id", filter=Q(ok=True)),
            failed_count=Count("id", filter=Q(ok=False)),
        )
    }
    top = now.replace(minute=0, second=0, microsecond=0)
    hours = [top - timezone.timedelta(hours=n) for n in range(23, -1, -1)]
    return json.dumps(
        {
            "labels": [localtime(h).strftime("%H:00") for h in hours],
            "datasets": [
                {
                    "label": "Succeeded",
                    "data": [counted.get(h, {}).get("ok_count", 0) for h in hours],
                    "backgroundColor": CHART_OK,
                },
                {
                    "label": "Failed",
                    "data": [counted.get(h, {}).get("failed_count", 0) for h in hours],
                    "backgroundColor": CHART_FAILED,
                },
            ],
        }
    )


# Unfold's defaults draw 4px bars and no stack. `data-options` replaces
# them wholesale, so every option the chart needs is here.
POLL_CHART_OPTIONS = json.dumps(
    {
        "animation": False,
        "responsive": True,
        "maintainAspectRatio": False,
        "scales": {
            "x": {"stacked": True, "grid": {"display": False}},
            "y": {"stacked": True, "beginAtZero": True, "ticks": {"precision": 0}},
        },
        "plugins": {"legend": {"align": "end", "labels": {"boxWidth": 10}}},
    }
)


def _failure_causes(day_ago):
    """The last day's failures, grouped by cause.

    Twenty-one identical DNS errors are one fact, not twenty-one.
    """
    from polling.models import PollRun

    groups = {}
    runs = (
        PollRun.objects.filter(ok=False, started_at__gte=day_ago)
        .select_related("poller__service")
        .order_by("-started_at")
    )
    for run in runs:
        cause = run.error_type or "Unrecorded"
        group = groups.setdefault(
            cause,
            {
                "cause": cause,
                "count": 0,
                "services": [],
                "last_at": run.started_at,
                "message": run.error,
            },
        )
        group["count"] += 1
        name = str(run.poller.service)
        if name not in group["services"]:
            group["services"].append(name)
    return sorted(groups.values(), key=lambda g: -g["count"])


def _ago(when, now):
    if when is None:
        return "never"
    minutes = int((now - when).total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    if minutes < 60 * 48:
        return f"{minutes // 60}h ago"
    return f"{minutes // 1440}d ago"


AUDIT_FIELDS = ["created_at", "updated_at", "created_by", "updated_by"]


class BaseModelAdmin:
    """Options every changelist in this project wants.

    Only names that exist in the installed Unfold. `compressed_fields`,
    for one, is not in 0.104 and setting it would be a silent no-op.
    """

    list_filter_sheet = True
    list_filter_submit = True
    list_fullwidth = True
    warn_unsaved_form = True
    list_per_page = 25

    def get_readonly_fields(self, request, obj=None):
        """Show the audit trail without offering to edit it."""
        fields = list(super().get_readonly_fields(request, obj))
        return fields + [f for f in AUDIT_FIELDS if f not in fields]

    def save_model(self, request, obj, form, change):
        """Stamp who did it.

        The fields are not editable, so they can only be set here. Left
        alone they stayed null forever, which is an audit trail that
        records nothing.
        """
        if not change and getattr(obj, "created_by_id", None) is None:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """The same stamp for anything edited through an inline."""
        for instance in formset.save(commit=False):
            if instance.pk is None and getattr(instance, "created_by_id", None) is None:
                instance.created_by = request.user
            instance.updated_by = request.user
            instance.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()


class PollerWrittenAdmin(BaseModelAdmin):
    """A record the poller writes. Readable here, never editable.

    `apply_fetch` and `poll_service` own these tables. A hand-written
    row invents history the API then serves. Or it trips a constraint
    the poller relies on. The next poll overwrites the edit anyway.

    Only the three permissions are refused. Django still renders the
    detail page read-only, so a poll error stays readable.

    Seed a database with `just seed-dev`, which polls for real.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Lower is worse, so the scale runs danger to success.
SEVERITY_VARIANTS = {
    Severity.MAJOR_OUTAGE.label: "danger",
    Severity.PARTIAL_OUTAGE.label: "danger",
    Severity.DEGRADED.label: "warning",
    Severity.UNKNOWN.label: "default",
    Severity.MAINTENANCE.label: "info",
    Severity.OPERATIONAL.label: "success",
}


def severity_label(value):
    return Severity(value).label if value is not None else "—"


class ScopedAutocompleteSelect(AutocompleteSelect):
    """The admin's autocomplete, narrowed to the row that asked.

    The endpoint is shared by every autocomplete and is told which field
    is asking, never which record. On its own it offers every row of the
    target model, so a component would be offered every service's
    components. The scope goes on the URL and the target admin reads it
    back with `ScopedAutocompleteMixin`.
    """

    def __init__(self, *args, scope=None, **kwargs):
        self.scope = {k: v for k, v in (scope or {}).items() if v}
        super().__init__(*args, **kwargs)

    def get_url(self):
        url = super().get_url()
        return f"{url}?{urlencode(self.scope)}" if self.scope else url


class ScopedAutocompleteMixin:
    """Read back the scope a widget put on the autocomplete URL.

    Each name is both the parameter and the field it filters on. Without
    a scope the results are unchanged, so the same admin still serves
    every other autocomplete that points at it.
    """

    autocomplete_scope: tuple[str, ...] = ()

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        for name in self.autocomplete_scope:
            value = request.GET.get(name)
            if not value:
                continue
            try:
                queryset = queryset.filter(**{name: UUID(value)})
            except ValueError:
                # A scope nobody can satisfy is safer than none at all.
                queryset = queryset.none()
        return queryset, may_have_duplicates


def audit_section():
    """The trail, folded away at the end of every form.

    It is the same four fields on every record. Nobody opens a form to
    read them. So it closes, and it sits last.
    """
    return (_("Audit"), {"classes": ["collapse"], "fields": list(AUDIT_FIELDS)})


def date_span(start, end):
    """The stretch of time a row covers.

    A span with no end is still running, and one inside a single day
    would print that day twice. Neither is written out.
    """
    if start is None:
        return "—"
    start = localtime(start)
    opens = date_format(start, "j M Y, H:i")
    if end is None:
        return f"{opens} →"
    end = localtime(end)
    closes = "H:i" if start.date() == end.date() else "j M Y, H:i"
    return f"{opens} → {date_format(end, closes)}"


def record_column(description):
    """The record's own name, for the first column of a changelist.

    Django wraps the first column in the link to the record. A foreign
    key there reads as the related thing but opens this one. The related
    thing is then left with no link. Naming the record frees the key to
    go where it says.
    """

    @display(description=description)
    def column(self, obj):
        return str(obj)

    return column


def change_link(obj, label=None):
    """A link to another record's own page.

    Every table is a place you arrive from somewhere else. A related
    column should carry you on, not print a name and stop.
    """
    if obj is None:
        return "—"
    opts = obj._meta
    return format_html(
        '<a href="{}" class="text-primary-600 dark:text-primary-500">{}</a>',
        reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk]),
        label or str(obj),
    )


def filtered_list(model_admin_path, label, count=None, **filters):
    """One entry for a `View` dropdown: a changelist, already filtered.

    The count goes on the label. A link to nothing reads like a link to
    something until you open it.
    """
    query = "&".join(f"{k}={v}" for k, v in filters.items())
    title = label if count is None else f"{label} ({count})"
    return {"title": title, "link": f"{reverse(model_admin_path)}?{query}"}


def related_count(queryset, group_by, ref="pk"):
    """How many rows are on the other end, without joining to fetch them.

    Several counts on one row multiply into one another. Each is a
    join, so a service is read once per component per event. Each count
    asks its own question instead.
    """
    counted = (
        queryset.filter(**{group_by: OuterRef(ref)})
        .order_by()
        .values(group_by)
        .annotate(total=Count("pk"))
        .values("total")
    )
    return Coalesce(Subquery(counted, output_field=IntegerField()), 0)


def poll_run_link(obj):
    """A link to the poll that wrote this row.

    Null on anything seeded by hand, and on rows written before the link
    existed. A reading with no provenance is exactly what this is for.
    """
    return change_link(obj.poll_run)


def phase_label(event):
    """The phase's own label, read through the event's kind.

    `phase` carries no choices. An incident and a maintenance window
    move through different ones. A flat enum would claim `scheduled` is
    valid on an incident. So the label comes from the enum that kind
    names.
    """
    phases = EVENT_PHASES_BY_KIND.get(event.kind)
    if phases is None:
        return event.phase
    try:
        return phases(event.phase).label
    except ValueError:
        # A provider can invent a phase we have not seen.
        return event.phase


class InheritedDefaultsMixin:
    """Say what a blank tuning field will actually do.

    The three Poller intervals fall back to a deployment setting. The
    form showed three empty boxes and did not say so.

    The text is built here, not as model help_text. Otherwise a settings
    change wants a migration, to restate a number the database never
    stores.
    """

    INHERITED_DEFAULTS = {
        "interval_seconds": "POLL_INTERVAL_SECONDS",
        "cooldown_seconds": "POLL_COOLDOWN_SECONDS",
        "max_interval_seconds": "POLL_MAX_INTERVAL_SECONDS",
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        setting = self.INHERITED_DEFAULTS.get(db_field.name)
        if field is not None and setting is not None:
            field.help_text = _(
                "Leave blank to use the deployment default of %(seconds)s seconds."
            ) % {"seconds": getattr(settings, setting)}
        return field
