from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    RangeDateTimeFilter,
)
from unfold.decorators import display

from authentication.models import MagicLinkToken, User
from common.admin import BaseModelAdmin, change_link, record_column


@admin.register(User)
class UserAdmin(BaseModelAdmin, ModelAdmin):
    list_display = [
        "display_user",
        "is_active",
        "is_staff",
        "last_login",
        "last_active_at",
    ]
    search_fields = ["email"]
    list_filter = [
        "is_active",
        "is_staff",
        "is_superuser",
        ("last_login", RangeDateTimeFilter),
        ("last_active_at", RangeDateTimeFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    ordering = ["-created_at"]

    @display(description=_("User"), header=True, ordering="email")
    def display_user(self, obj):
        return [obj.email, str(obj.id), obj.email[:2].upper()]


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(BaseModelAdmin, ModelAdmin):
    list_display = [
        "display_link",
        "display_user",
        "display_state",
        "expires_at",
        "used_at",
    ]
    display_link = record_column(_("Link"))
    search_fields = ["user__email"]
    list_filter = [
        ("user", AutocompleteSelectFilter),
        ("created_at", RangeDateTimeFilter),
        ("expires_at", RangeDateTimeFilter),
        ("used_at", RangeDateTimeFilter),
    ]
    autocomplete_fields = ["user"]
    ordering = ["-created_at"]

    @display(description=_("User"), ordering="user__email")
    def display_user(self, obj):
        return change_link(obj.user)

    @display(
        description=_("State"),
        label={"Usable": "success", "Used": "default", "Expired": "warning"},
    )
    def display_state(self, obj):
        if obj.used_at:
            return "Used"
        return "Usable" if obj.is_usable else "Expired"
