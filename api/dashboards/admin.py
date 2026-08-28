from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import AutocompleteSelectFilter, RangeDateTimeFilter
from unfold.decorators import display

from common.admin import BaseModelAdmin, change_link, record_column
from dashboards.models import Dashboard, DashboardItem


class DashboardItemInline(TabularInline):
    model = DashboardItem
    extra = 0
    tab = True
    autocomplete_fields = ["component"]


@admin.register(Dashboard)
class DashboardAdmin(BaseModelAdmin, ModelAdmin):
    list_display = ["display_board", "display_owner", "is_default", "item_count"]
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

    def has_delete_permission(self, request, obj=None):
        """An owner keeps their last board, so it is not offered.

        The model refuses it too. This is so the button is not there to
        press in the first place.
        """
        if obj is not None and not obj.owner.dashboards.exclude(pk=obj.pk).exists():
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        """Delete one at a time, so the rule on the model is reached.

        A bulk delete goes straight to SQL. The last board of an owner
        would go with it, and they would sign in to nothing.
        """
        kept = []
        for board in queryset:
            try:
                board.delete()
            except ValidationError:
                kept.append(str(board))
        if kept:
            self.message_user(
                request,
                _("Kept %s. An owner keeps their last board.") % ", ".join(kept),
                messages.WARNING,
            )

    @display(description=_("Owner"), ordering="owner__email")
    def display_owner(self, obj):
        return change_link(obj.owner)

    @display(description=_("Board"), header=True, ordering="name")
    def display_board(self, obj):
        return [obj.name, obj.owner.email]

    @display(description=_("Tracked"))
    def item_count(self, obj):
        return obj.items.count()


@admin.register(DashboardItem)
class DashboardItemAdmin(BaseModelAdmin, ModelAdmin):
    list_display = ["display_item", "display_dashboard", "display_component"]
    display_item = record_column(_("Tracked"))
    search_fields = ["dashboard__name", "component__name"]
    list_filter = [("dashboard", AutocompleteSelectFilter)]
    autocomplete_fields = ["dashboard", "component"]

    @display(description=_("Board"), ordering="dashboard__name")
    def display_dashboard(self, obj):
        return change_link(obj.dashboard)

    @display(description=_("Component"), ordering="component__name")
    def display_component(self, obj):
        return change_link(obj.component)
