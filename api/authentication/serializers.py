from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from authentication.models import User
from common.mixins import FieldsMixin


class MeSerializer(FieldsMixin, serializers.ModelSerializer):
    default_dashboard_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "default_dashboard_id"]

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_default_dashboard_id(self, user):
        # Task 8 adds the `dashboards` relation and its default-dashboard signal.
        dashboard = getattr(user, "dashboards", None)
        if dashboard is None:
            return None
        row = dashboard.filter(is_default=True).first()
        return str(row.id) if row else None


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="15 minutes")
    refresh = serializers.CharField(help_text="30 days, rotating")
