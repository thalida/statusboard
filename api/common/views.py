from django.conf import settings
from django.urls import reverse
from django.views.generic import TemplateView
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.choices import StatusPageProvider
from common.serializers import MetaSerializer
from status.choices import EVENT_PHASES_BY_KIND, EventKind, Severity, StatusSource


def _labels(choices):
    return {str(value): label for value, label in choices.choices}


class MetaView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: MetaSerializer})
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


class ApiDocsView(TemplateView):
    """Scalar at the root, reading the generated schema.

    Public, because /schema/ already is. Gating the page while the
    schema it renders stays open would protect nothing.

    The view lives in `common`, not in a `docs` app. The repository has a
    top-level `docs/` for the spec and the contract. A second thing called
    docs would be one name for two ideas.
    """

    template_name = "common/api_docs.html"

    DESCRIPTION = (
        "The Statusboard API. Track services from a catalog and read their "
        "current status, incidents and maintenance windows."
    )

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            schema_url=reverse("schema"), description=self.DESCRIPTION, **kwargs
        )
