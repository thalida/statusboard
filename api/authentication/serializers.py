from rest_framework import serializers

from authentication.models import User
from common.mixins import FieldsMixin


class MeSerializer(FieldsMixin, serializers.ModelSerializer):
    default_dashboard_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "default_dashboard_id"]

    def get_default_dashboard_id(self, user):
        # Task 8 adds the `dashboards` relation and its default-dashboard signal.
        dashboard = getattr(user, "dashboards", None)
        if dashboard is None:
            return None
        row = dashboard.filter(is_default=True).first()
        return str(row.id) if row else None
