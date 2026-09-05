from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import BooleanField, ExpressionWrapper, F, Q
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import AutocompleteSelectFilter, RangeDateTimeFilter
from unfold.decorators import display

from common.admin import (
    BaseModelAdmin,
    ScopedAutocompleteMixin,
    audit_section,
    change_link,
    record_column,
)
from common.queries import related_count
from dashboards.models import Dashboard, DashboardItem


class DashboardItemInline(TabularInline):
    model = DashboardItem
    extra = 0
    tab = True
    autocomplete_fields = ["component"]


# Which board is the default is a pointer on the user. So it is a
# comparison here, not a column to read.
IS_DEFAULT = ExpressionWrapper(
    Q(owner__default_dashboard=F("pk")), output_field=BooleanField()
)


class HoldsItemsFilter(admin.SimpleListFilter):
    """Whether a board holds anything.

    The count is a column and was not a filter. An empty board is what
    a person opens the list to find.
    """

    title = _("Tracked")
    parameter_name = "holds"

    def lookups(self, request, model_admin):
        return [("1", _("Holds components")), ("0", _("Empty"))]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        return queryset.filter(items__isnull=self.value() == "0").distinct()


class DefaultBoardFilter(admin.SimpleListFilter):
    """Whether a board is the one its owner opens.

    There is no column to filter on. The answer is whether the owner
    points back at this row.
    """

    title = _("Default")
    parameter_name = "default"

    def lookups(self, request, model_admin):
        return [("1", _("Yes")), ("0", _("No"))]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        return queryset.filter(default_for_owner=self.value() == "1")


@admin.register(Dashboard)
class DashboardAdmin(ScopedAutocompleteMixin, BaseModelAdmin, ModelAdmin):
    # A person picking their default board is offered their own.
    autocomplete_scope = ("owner",)
    # No `default` column. The pointer lives on the user, as
    # `default_dashboard`. It is a fact about the owner, not the board.
    # It stays on the form, and its filter stays.
    list_display = ["display_board", "display_owner", "item_count"]
    search_fields = ["name", "owner__email"]
    list_filter = [
        ("owner", AutocompleteSelectFilter),
        DefaultBoardFilter,
        HoldsItemsFilter,
        ("created_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["owner"]
    inlines = [DashboardItemInline]
    # Both are read from elsewhere. The default is a pointer on the
    # owner, and the count is the rows below.
    readonly_fields = ["display_default", "item_count"]
    fieldsets = [
        (None, {"fields": ["owner", "name", "display_default", "item_count"]}),
        audit_section(),
    ]

    def get_queryset(self, request):
        # The count was a query per row. It is one subquery now.
        return (
            super()
            .get_queryset(request)
            .select_related("owner")
            .annotate(
                tracked=related_count(DashboardItem.objects, "dashboard"),
                default_for_owner=IS_DEFAULT,
            )
        )

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

    @display(
        description=_("Default"),
        label={"Default": "success", "—": "default"},
        ordering="default_for_owner",
    )
    def display_default(self, obj):
        return "Default" if obj.default_for_owner else "—"

    @display(description=_("Owner"), ordering="owner__email")
    def display_owner(self, obj):
        return change_link(obj.owner)

    @display(description=_("Board"), header=True, ordering="name")
    def display_board(self, obj):
        return [obj.name, obj.owner.email]

    @display(description=_("Tracked"), ordering="tracked")
    def item_count(self, obj):
        return obj.tracked


@admin.register(DashboardItem)
class DashboardItemAdmin(BaseModelAdmin, ModelAdmin):
    list_display = ["display_item", "display_dashboard", "display_component"]
    display_item = record_column(_("Item"))
    search_fields = [
        "dashboard__name",
        "dashboard__owner__email",
        "component__name",
        "component__external_id",
        "component__service__name",
    ]
    list_filter = [
        ("dashboard__owner", AutocompleteSelectFilter),
        ("dashboard", AutocompleteSelectFilter),
        ("component__service", AutocompleteSelectFilter),
        ("component", AutocompleteSelectFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["dashboard", "component"]
    fieldsets = [
        (None, {"fields": ["dashboard", "component"]}),
        audit_section(),
    ]

    @display(description=_("Board"), ordering="dashboard__name")
    def display_dashboard(self, obj):
        return change_link(obj.dashboard)

    @display(description=_("Component"), ordering="component__name")
    def display_component(self, obj):
        return change_link(obj.component)
