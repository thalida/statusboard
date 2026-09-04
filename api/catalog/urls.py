from django.urls import path

from catalog.views.components import ComponentDetailView, ComponentListView
from catalog.views.imports import CatalogImportView
from catalog.views.requests import ServiceRequestView
from catalog.views.services import ServiceDetailView

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
