from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.token_blacklist.admin import (
    BlacklistedTokenAdmin as BaseBlacklistedTokenAdmin,
)
from rest_framework_simplejwt.token_blacklist.admin import (
    OutstandingTokenAdmin as BaseOutstandingTokenAdmin,
)
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    RangeDateTimeFilter,
)
from unfold.decorators import display

from api.defaults import SYSTEM_EMAIL
from authentication.models import MagicLinkToken, User
from common.admin import (
    BaseModelAdmin,
    ScopedAutocompleteSelect,
    audit_section,
    change_link,
    record_column,
)
from dashboards.models import Dashboard


class UserForm(forms.ModelForm):
    """The user form, with the password left where it is.

    A plain field renders the stored hash in an editable box. Typing a
    new password there writes it in as the hash. The account can never
    sign in again, and the password sits in the column in the clear.

    This shows the hash and takes nothing.

    There is no change-password screen to link to. Signing in is a magic
    link, and the only password is the seeded admin's.
    """

    password = ReadOnlyPasswordHashField(
        label=_("Password"),
        help_text=_("Not stored in a form anybody can read."),
    )

    class Meta:
        model = User
        fields = "__all__"

    def clean_password(self):
        # The field is shown, never taken. Keep what is stored.
        return self.initial["password"]


@admin.register(User)
class UserAdmin(BaseModelAdmin, ModelAdmin):
    form = UserForm
    # A person can have many boards, and a plain dropdown would list
    # every board of every owner.
    autocomplete_fields = ["default_dashboard"]
    # Django orders the form by the model's fields, and
    # PermissionsMixin declares its own first. So `is_superuser` sat
    # above the address, away from the two flags it belongs with.
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        (_("Default board"), {"fields": ["default_dashboard"]}),
        (
            _("Access"),
            {"fields": ["is_active", "is_bot", "is_staff", "is_superuser"]},
        ),
        (
            _("Permissions"),
            {"classes": ["collapse"], "fields": ["groups", "user_permissions"]},
        ),
        (_("Activity"), {"fields": ["last_login", "last_active_at"]}),
        audit_section(),
    ]

    def get_form(self, request, obj=None, **kwargs):
        # The widget needs to know whose boards to offer, and this is
        # where the row being edited is known.
        request._editing = obj
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "default_dashboard":
            owner = getattr(request, "_editing", None)
            kwargs["widget"] = ScopedAutocompleteSelect(
                db_field,
                self.admin_site,
                scope={"owner": owner.pk if owner else None},
            )
            if owner is not None:
                # Also the server's half of it. The URL narrows what is
                # offered; this refuses anything else that is posted.
                kwargs["queryset"] = Dashboard.objects.filter(owner=owner)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    list_display = [
        "display_user",
        "display_default_board",
        "display_active",
        "display_bot",
        "display_staff",
        "display_superuser",
        "last_login",
        "last_active_at",
    ]
    search_fields = ["email"]
    list_filter = [
        "is_active",
        "is_bot",
        "is_staff",
        "is_superuser",
        ("last_login", RangeDateTimeFilter),
        ("last_active_at", RangeDateTimeFilter),
        ("created_at", RangeDateTimeFilter),
    ]
    ordering = ["-created_at"]

    def has_delete_permission(self, request, obj=None):
        """The system account stays. It signs rows it did not sign twice.

        Removing it blanks the author on everything the importer and
        the signals made. The next migrate makes a new one, and it is
        not the same account.
        """
        if obj is not None and obj.email == SYSTEM_EMAIL:
            return False
        return super().has_delete_permission(request, obj)

    # Django's own labels read "active", "staff status" and "superuser
    # status". The three sit side by side, so they read as a set here.
    @display(description=_("Board"), ordering="default_dashboard__name")
    def display_default_board(self, obj):
        return change_link(obj.default_dashboard)

    @display(description=_("Bot"), boolean=True, ordering="is_bot")
    def display_bot(self, obj):
        return obj.is_bot

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
    # The token is the credential. It is shown, never typed over: a new
    # one by hand is a link nobody was sent.
    readonly_fields = ["token"]
    fieldsets = [
        (None, {"fields": ["user", "token"]}),
        (_("Validity"), {"fields": ["expires_at", "used_at"]}),
        audit_section(),
    ]

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


# Django registers Group and simplejwt registers its two token tables, all
# with plain `admin.ModelAdmin`. Inside Unfold those pages render
# unstyled: no sidebar, no filters, a different form. Rebuilding each
# class over `ModelAdmin` keeps the behaviour and takes the chrome. The
# same is done for the beat schedules in `polling.admin`.
RESTYLED_AUTH_ADMIN = [
    (Group, BaseGroupAdmin),
    (OutstandingToken, BaseOutstandingTokenAdmin),
    (BlacklistedToken, BaseBlacklistedTokenAdmin),
]

for _model, _base in RESTYLED_AUTH_ADMIN:
    admin.site.unregister(_model)
    admin.site.register(
        _model, type(f"Unfold{_base.__name__}", (_base, ModelAdmin), {})
    )
