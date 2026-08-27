from django.urls import path

from catalog.views import (
    CatalogImportView,
    ServiceComponentListView,
    ServiceDetailView,
    ServiceEventListView,
    ServiceListView,
)

urlpatterns = [
    # Above the <slug:slug> route so it is not shadowed.
    path("catalog/import/", CatalogImportView.as_view(), name="catalog-import"),
    path("catalog/services/", ServiceListView.as_view(), name="service-list"),
    path(
        "catalog/services/<slug:slug>/",
        ServiceDetailView.as_view(),
        name="service-detail",
    ),
    path(
        "catalog/services/<slug:slug>/components/",
        ServiceComponentListView.as_view(),
        name="service-components",
    ),
    path(
        "catalog/services/<slug:slug>/events/",
        ServiceEventListView.as_view(),
        name="service-events",
    ),
]
