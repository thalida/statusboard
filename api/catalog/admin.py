from django.contrib import admin
from unfold.admin import ModelAdmin

from catalog.models import Poller, Service, ServiceComponent, StatusPage


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ["name", "slug", "watcher_count", "is_featured"]
    search_fields = ["name", "slug"]
    list_filter = ["is_featured"]


@admin.register(StatusPage)
class StatusPageAdmin(ModelAdmin):
    list_display = ["service", "provider", "url"]
    list_filter = ["provider"]


@admin.register(Poller)
class PollerAdmin(ModelAdmin):
    list_display = [
        "service",
        "is_paused",
        "consecutive_failure_count",
        "last_success_at",
        "next_at",
    ]
    list_filter = ["is_paused"]
    # The failing services must be findable without a query.
    ordering = ["-consecutive_failure_count"]


@admin.register(ServiceComponent)
class ServiceComponentAdmin(ModelAdmin):
    list_display = ["name", "service", "is_overall", "archived_at"]
    list_filter = ["is_overall", "service"]
    search_fields = ["name", "external_id"]
