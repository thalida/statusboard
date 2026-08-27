from django.contrib import admin
from unfold.admin import ModelAdmin

from authentication.models import MagicLinkToken, User


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ["email", "is_active", "is_staff", "last_login", "last_active_at"]
    search_fields = ["email"]


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(ModelAdmin):
    list_display = ["user", "expires_at", "used_at"]
