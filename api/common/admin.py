"""Admin-wide callbacks: the environment badge and the dashboard."""

from django.conf import settings
from django.db.models import Count, Min, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from status.choices import Severity


def environment_callback(request):
    """Colour the banner by database.

    Acting on production while believing it is local is the mistake worth
    making loud.
    """
    return {
        "local": ["Local", "info"],
        "staging": ["Staging", "warning"],
        "production": ["Production", "danger"],
    }.get(settings.ENVIRONMENT, [settings.ENVIRONMENT.title(), "warning"])


def environment_prefix_callback(request):
    """Put the environment in the browser tab, where a stray tab shows it."""
    return "" if settings.ENVIRONMENT == "production" else f"[{settings.ENVIRONMENT}]"


def dashboard_callback(request, context):
    """Answer one question: is polling healthy?

    We are the thing that tells you when services break. A stalled poller
    shows every board a stale green, which is worse than showing nothing,
    so the landing page leads with the poller and not with row counts.
    """
    from catalog.models import Service
    from polling.models import Poller, PollRun

    now = timezone.now()
    day_ago = now - timezone.timedelta(hours=24)

    pollers = Poller.objects.aggregate(
        total=Count("id"),
        failing=Count("id", filter=Q(consecutive_failure_count__gt=0)),
        paused=Count("id", filter=Q(is_paused=True)),
        overdue=Count("id", filter=Q(next_at__lt=now, is_paused=False)),
        oldest_success=Min("last_success_at"),
    )
    runs = PollRun.objects.filter(started_at__gte=day_ago).aggregate(
        total=Count("id"), failed=Count("id", filter=Q(ok=False))
    )
    ok_rate = (
        round(100 * (runs["total"] - runs["failed"]) / runs["total"])
        if runs["total"]
        else None
    )

    context["cards"] = [
        {
            "title": "Services tracked",
            "value": Service.objects.filter(watcher_count__gt=0).count(),
            "icon": "lan",
            "detail": f"{Service.objects.count()} in the catalog",
        },
        {
            "title": "Pollers in backoff",
            "value": pollers["failing"],
            "icon": "error",
            "danger": pollers["failing"] > 0,
            "detail": f"{pollers['paused']} paused, {pollers['overdue']} overdue",
        },
        {
            "title": "Poll success, 24h",
            "value": "—" if ok_rate is None else f"{ok_rate}%",
            "icon": "check_circle",
            "danger": ok_rate is not None and ok_rate < 95,
            "detail": f"{runs['total']} runs, {runs['failed']} failed",
        },
        {
            "title": "Oldest successful poll",
            "value": _ago(pollers["oldest_success"], now),
            "icon": "schedule",
            "detail": "Across every poller",
        },
    ]
    context["recent_failures"] = (
        PollRun.objects.filter(ok=False)
        .select_related("poller__service")
        .order_by("-started_at")[:8]
    )
    return context


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

    `apply_fetch` and `poll_service` own these tables. A hand-written row
    either invents history the API then serves, or trips a constraint the
    poller relies on, and the next poll overwrites the edit anyway.

    Only the three permissions are refused. Django still renders the
    detail page read-only, so a poll error stays readable.

    ADMIN_EDITABLE_POLLER_DATA lifts this for seeding a local database by
    hand. It is off unless .env.local sets it.
    """

    def has_add_permission(self, request, obj=None):
        return settings.ADMIN_EDITABLE_POLLER_DATA

    def has_change_permission(self, request, obj=None):
        return settings.ADMIN_EDITABLE_POLLER_DATA

    def has_delete_permission(self, request, obj=None):
        return settings.ADMIN_EDITABLE_POLLER_DATA


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


def poll_run_link(obj):
    """A link to the poll that wrote this row.

    Null on anything seeded by hand, and on rows written before the link
    existed. A reading with no provenance is exactly what this is for.
    """
    run = obj.poll_run
    if run is None:
        return "—"
    return format_html(
        '<a href="{}" class="text-primary-600 dark:text-primary-500">{}</a>',
        reverse("admin:polling_pollrun_change", args=[run.pk]),
        run,
    )
