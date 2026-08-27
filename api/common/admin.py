"""Admin-wide callbacks: the environment badge and the dashboard."""

from django.conf import settings
from django.db.models import Count, Min, Q
from django.utils import timezone


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
    from catalog.models import Poller, Service
    from status.models import PollRun

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


class PollerWrittenAdmin(BaseModelAdmin):
    """A record the poller writes. Readable here, never editable.

    `apply_fetch` and `poll_service` own these tables. A hand-written row
    either invents history the API then serves, or trips a constraint the
    poller relies on, and the next poll overwrites the edit anyway.

    Only the three permissions are refused. Django still renders the
    detail page read-only, so a poll error stays readable.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
