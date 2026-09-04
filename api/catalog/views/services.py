from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny

from catalog.models import Service
from catalog.serializers import ServiceSerializer
from common.filters import FieldsBackend
from common.serializers import ErrorSerializer


@extend_schema_view(
    get=extend_schema(responses={200: ServiceSerializer, 404: ErrorSerializer})
)
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
