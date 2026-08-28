from rest_framework import serializers

from authentication.models import User
from common.mixins import FieldsMixin


class MeSerializer(FieldsMixin, serializers.ModelSerializer):
    # The column is the answer, so there is nothing to look up.
    default_dashboard_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "email", "default_dashboard_id"]


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="15 minutes")
    refresh = serializers.CharField(help_text="30 days, rotating")
