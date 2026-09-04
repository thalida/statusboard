import requests
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.defaults import Throttle
from catalog.models import Service, ServiceRequest, StatusPage
from catalog.serializers import (
    ImportRequestSerializer,
    ServiceRequestSerializer,
    ServiceSerializer,
)
from common.errors import NoStatusPageFound, ProviderUnreachable
from common.filters import FieldsBackend
from polling.importer import import_from_url


class ServiceDetailView(generics.RetrieveAPIView):
    """The service page's header and its About tab.

    There is no list. Discover searches components, and the signed-out
    board lists overall components. So nothing asked a service
    collection a question.
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"
    serializer_class = ServiceSerializer
    filter_backends = [FieldsBackend]
    # get_queryset reads the request, which schema generation has not
    # set. This names the model without running it.
    queryset = Service.objects.none()

    def get_queryset(self):
        return Service.objects.for_display(self.request.user)


class CatalogImportView(APIView):
    """Add a service by pasting the address of its status page.

    Its own path, because the body is a URL rather than a service. A
    later create that takes a service body then does not overload this
    one.
    """

    permission_classes = [AllowAny]
    # Every call makes the server fetch a URL somebody else chose.
    throttle_scope = Throttle.IMPORT

    @extend_schema(
        request=ImportRequestSerializer,
        responses={
            200: ServiceSerializer,
            201: ServiceSerializer,
            400: OpenApiResponse(description="Missing or malformed status_page_url."),
        },
    )
    def post(self, request):
        body = ImportRequestSerializer(data=request.data)
        if not body.is_valid():
            return Response(body.errors, status=400)
        url = body.validated_data["status_page_url"]
        try:
            service, created = import_from_url(url)
        except ValueError as error:
            # `identify` raises this when no adapter could read the page.
            # It is the ordinary outcome of pasting the wrong address,
            # and it used to reach the caller as a 500.
            raise NoStatusPageFound(str(error)) from error
        except requests.RequestException as error:
            raise ProviderUnreachable(f"{url} could not be read: {error}") from error
        return Response(
            ServiceSerializer(service, context={"request": request}).data,
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )


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
