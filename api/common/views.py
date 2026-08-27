from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
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


@method_decorator(staff_member_required, name="dispatch")
class ApiDocsView(TemplateView):
    """Scalar, inside the admin, reading the generated schema.

    It lives here rather than in its own `docs` app: the repository already
    has a top-level `docs/` holding the spec and the contract, and a second
    thing called docs next to it is one name for two ideas.
    """

    template_name = "common/api_docs.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(schema_url=reverse("schema"), **kwargs)
