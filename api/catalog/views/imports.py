import requests
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.defaults import Throttle
from catalog.models import Service
from catalog.serializers import ImportRequestSerializer, ServiceSerializer
from common.errors import NoStatusPageFound, ProviderUnreachable
from polling.importer import import_from_url


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
        # Read again, after the import. `ServiceSerializer` reads the
        # counts `for_display` annotates, and the import returns a
        # plain row.
        row = Service.objects.for_display(request.user).get(pk=service.pk)
        return Response(
            ServiceSerializer(row, context={"request": request}).data,
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )
