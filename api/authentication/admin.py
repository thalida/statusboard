from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    RangeDateTimeFilter,
)
from unfold.decorators import display

from authentication.models import SYSTEM_EMAIL, MagicLinkToken, User
from common.admin import BaseModelAdmin, change_link, record_column


@admin.register(User)
class UserAdmin(BaseModelAdmin, ModelAdmin):
    list_display = [
        "display_user",
        "display_active",
        "display_staff",
        "display_superuser",
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

    def has_delete_permission(self, request, obj=None):
        """The system account stays. It signs rows it did not sign twice.

        Removing it blanks the author on everything the importer and the
        signals made, and the next migrate makes a new one that is not
        the same account.
        """
        if obj is not None and obj.email == SYSTEM_EMAIL:
            return False
        return super().has_delete_permission(request, obj)

    # Django's own labels read "active", "staff status" and "superuser
    # status". The three sit side by side, so they read as a set here.
    @display(description=_("Active"), boolean=True, ordering="is_active")
    def display_active(self, obj):
        return obj.is_active

    @display(description=_("Staff"), boolean=True, ordering="is_staff")
    def display_staff(self, obj):
        return obj.is_staff

    @display(description=_("Superuser"), boolean=True, ordering="is_superuser")
    def display_superuser(self, obj):
        return obj.is_superuser

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
    # Never the token. It is a credential, and a search term is kept in
    # the address bar, in history and in the log.
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
