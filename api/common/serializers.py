from enum import StrEnum

from rest_framework import serializers


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


class MetaSerializer(serializers.Serializer):
    """Deployment-wide configuration. Nothing here is a user preference."""

    poll_interval_seconds = serializers.IntegerField()
    poll_cooldown_seconds = serializers.IntegerField()
    default_page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    enums = serializers.DictField(
        help_text="Label maps for every enum, keyed by enum name."
    )
