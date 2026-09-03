from enum import StrEnum

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.mixins import FieldsMixin


class ErrorCode(StrEnum):
    """What a failure calls itself.

    A bare string would let a new code ship without the client knowing
    it exists. The handler that raises one is a file away from the
    schema that publishes them.
    """

    THROTTLED = "throttled"
    PROVIDER_UNREACHABLE = "provider_unreachable"
    NO_STATUS_PAGE_FOUND = "no_status_page_found"
    INVALID_OR_EXPIRED_TOKEN = "invalid_or_expired_token"
    NOT_FOUND = "not_found"


class ErrorSerializer(serializers.Serializer):
    """The one error shape. Every failure response uses it."""

    code = serializers.ChoiceField(choices=ErrorCode)
    detail = serializers.CharField()


class MetaSerializer(FieldsMixin, serializers.Serializer):
    """Deployment-wide configuration. Nothing here is a user preference."""

    poll_interval_seconds = serializers.IntegerField()
    poll_cooldown_seconds = serializers.IntegerField()
    default_page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    enums = serializers.SerializerMethodField()

    @extend_schema_field(
        serializers.DictField(
            help_text="Label maps for every enum, keyed by enum name."
        )
    )
    def get_enums(self, obj):
        """Keep only the enums a dotted `?fields=enums.<name>` names.

        `enums` is a plain dict, not a nested serializer, so
        `FieldsMixin` cannot prune inside it on its own. This reads the
        branch under "enums" and filters by hand instead. `MetaView`
        still names every enum in the one place it always has.
        """
        enums = obj["enums"]
        wanted = self.child_tree("enums")
        if not wanted:
            return enums
        return {name: labels for name, labels in enums.items() if name in wanted}
