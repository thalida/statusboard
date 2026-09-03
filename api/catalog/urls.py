from django.urls import include, path
from rest_framework.routers import SimpleRouter

from catalog.views import CatalogImportView, ServiceViewSet

router = SimpleRouter(trailing_slash=True)
# basename "service" gives service-list, service-detail, and one route per
# detail action: service-components and service-events.
router.register("catalog/services", ServiceViewSet, basename="service")

urlpatterns = [
    # Above the router so its slug route does not shadow it.
    path("catalog/import/", CatalogImportView.as_view(), name="catalog-import"),
    path("", include(router.urls)),
]
