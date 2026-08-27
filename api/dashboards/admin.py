from django.contrib import admin
from unfold.admin import ModelAdmin

from dashboards.models import Dashboard, DashboardItem


@admin.register(Dashboard)
class DashboardAdmin(ModelAdmin):
    list_display = ["name", "owner", "is_default"]


@admin.register(DashboardItem)
class DashboardItemAdmin(ModelAdmin):
    list_display = ["dashboard", "component"]
