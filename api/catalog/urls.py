from django.urls import path

from catalog.views import CatalogImportView, ServiceDetailView, ServiceRequestView
from catalog.views_components import ComponentDetailView, ComponentListView

urlpatterns = [
    path("catalog/import/", CatalogImportView.as_view(), name="catalog-import"),
    path(
        "catalog/requests/",
        ServiceRequestView.as_view(),
        name="catalog-request",
    ),
    # Above the service route, so `components` is never read as a slug.
    path(
        "catalog/components/",
        ComponentListView.as_view(),
        name="component-list",
    ),
    path(
        "catalog/components/<uuid:uuid>/",
        ComponentDetailView.as_view(),
        name="component-detail",
    ),
    path(
        "catalog/services/<slug:slug>/",
        ServiceDetailView.as_view(),
        name="service-detail",
    ),
]
