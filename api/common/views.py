from django.conf import settings
from django.db import connection
from django.urls import reverse
from django.views.generic import TemplateView
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.choices import StatusPageProvider
from common.serializers import MetaSerializer
from status.choices import (
    EVENT_PHASES_BY_KIND,
    EventKind,
    EventSource,
    Severity,
    StatusSource,
)


def _labels(choices):
    return {str(value): label for value, label in choices.choices}


class HealthView(APIView):
    """Whether this process can serve a request.

    The container restarts on a failure here, so it answers what a
    restart would fix. A reachable database is one: a pool that has lost
    its connections recovers. A provider being down is not.

    Excluded from the schema. It is how the deployment watches the
    process, and no client is written against it.
    """

    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(exclude=True)
    def get(self, request):
        connection.ensure_connection()
        return Response({"status": "ok"})


class MetaView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: MetaSerializer})
    def get(self, request):
        data = {
            "poll_interval_seconds": settings.POLL_INTERVAL_SECONDS,
            "poll_cooldown_seconds": settings.POLL_COOLDOWN_SECONDS,
            "default_page_size": settings.DEFAULT_PAGE_SIZE,
            "max_page_size": settings.MAX_PAGE_SIZE,
            "enums": {
                "severity": _labels(Severity),
                "status_source": _labels(StatusSource),
                "status_page_provider": _labels(StatusPageProvider),
                "event_kind": _labels(EventKind),
                "event_source": _labels(EventSource),
                "event_phase": {
                    str(kind): _labels(phases)
                    for kind, phases in EVENT_PHASES_BY_KIND.items()
                },
            },
        }
        # `Response(data)` skips `MetaSerializer`, so `?fields=` never
        # pruned. `FieldsMixin` prunes at construction, on the instance.
        return Response(MetaSerializer(data, context={"request": request}).data)


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
