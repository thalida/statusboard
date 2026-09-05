from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.defaults import Throttle
from catalog.models import ServiceRequest, StatusPage
from catalog.serializers import ServiceRequestSerializer
from common.serializers import ErrorSerializer


class ServiceRequestView(APIView):
    """ "Send this URL to us", from the Add-by-URL not-found screen.

    An import stores nothing about an attempt that failed, so this is
    where a dead end goes. Telling somebody to hunt for a better link
    assumes they have not already tried.
    """

    permission_classes = [AllowAny]
    # An anonymous write. Without this one person could inflate the
    # demand signal the admin list is ordered by.
    #
    # Its own scope, not IMPORT's. A failed import and the report that
    # follows it share one flow. One bucket would let the import spend
    # the report's budget.
    throttle_scope = Throttle.SERVICE_REQUEST

    @extend_schema(
        request=ServiceRequestSerializer,
        responses={
            202: OpenApiResponse(description="Recorded."),
            400: OpenApiResponse(description="Missing or malformed url."),
            429: OpenApiResponse(
                response=ErrorSerializer, description="Too many requests."
            ),
        },
    )
    def post(self, request):
        body = ServiceRequestSerializer(data=request.data)
        if not body.is_valid():
            return Response(body.errors, status=400)
        url = StatusPage.normalise_url(body.validated_data["url"])
        author = request.user if request.user.is_authenticated else None
        row, created = ServiceRequest.objects.get_or_create(
            url=url, defaults={"created_by": author, "updated_by": author}
        )
        if not created:
            # F() rather than a read and a write. Two people asking at
            # once would otherwise both write 2.
            ServiceRequest.objects.filter(pk=row.pk).update(
                request_count=F("request_count") + 1,
                last_requested_at=timezone.now(),
            )
        # Always 202, and always the same body. Anything else would
        # tell a stranger which URLs the catalog already holds.
        return Response(status=http.HTTP_202_ACCEPTED)
