from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import AutocompleteSelectFilter, RangeDateTimeFilter
from unfold.decorators import display

from common.admin import BaseModelAdmin
from dashboards.models import Dashboard, DashboardItem


class DashboardItemInline(TabularInline):
    model = DashboardItem
    extra = 0
    tab = True
    autocomplete_fields = ["component"]


@admin.register(Dashboard)
class DashboardAdmin(BaseModelAdmin, ModelAdmin):
    list_display = ["display_board", "owner", "is_default", "item_count"]
    search_fields = ["name", "owner__email"]
    list_filter = [
        "is_default",
        ("owner", AutocompleteSelectFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["owner"]
    inlines = [DashboardItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("owner")

    @display(description=_("Board"), header=True, ordering="name")
    def display_board(self, obj):
        return [obj.name, obj.owner.email]

    @display(description=_("Tracked"))
    def item_count(self, obj):
        return obj.items.count()


@admin.register(DashboardItem)
class DashboardItemAdmin(BaseModelAdmin, ModelAdmin):
    list_display = ["dashboard", "component"]
    search_fields = ["dashboard__name", "component__name"]
    list_filter = [("dashboard", AutocompleteSelectFilter)]
    autocomplete_fields = ["dashboard", "component"]
