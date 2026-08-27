from django.urls import path

from catalog.views import (
    ServiceComponentListView,
    ServiceDetailView,
    ServiceEventListView,
    ServiceListView,
)

urlpatterns = [
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
