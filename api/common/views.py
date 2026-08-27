from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.choices import StatusPageProvider
from status.choices import EVENT_PHASES_BY_KIND, EventKind, Severity, StatusSource


def _labels(choices):
    return {str(value): label for value, label in choices.choices}


class MetaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "poll_interval_seconds": settings.POLL_INTERVAL_SECONDS,
                "poll_cooldown_seconds": settings.POLL_COOLDOWN_SECONDS,
                "default_page_size": settings.DEFAULT_PAGE_SIZE,
                "max_page_size": settings.MAX_PAGE_SIZE,
                "enums": {
                    "severity": _labels(Severity),
                    "status_source": _labels(StatusSource),
                    "status_page_provider": _labels(StatusPageProvider),
                    "event_kind": _labels(EventKind),
                    "event_phase": {
                        str(kind): _labels(phases)
                        for kind, phases in EVENT_PHASES_BY_KIND.items()
                    },
                },
            }
        )
