from rest_framework import serializers

# The failure codes the contract names. A bare string would let any new
# code ship without the client knowing it exists.
ERROR_CODES = [
    "throttled",
    "provider_unreachable",
    "no_status_page_found",
    "invalid_or_expired_token",
    "not_found",
]


class ErrorSerializer(serializers.Serializer):
    """The one error shape. Every failure response uses it."""

    code = serializers.ChoiceField(choices=ERROR_CODES)
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
