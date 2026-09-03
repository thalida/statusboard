from django.urls import path

from dashboards.views import BoardComponentDetailView, BoardComponentListView

urlpatterns = [
    path(
        "dashboards/<uuid:uuid>/components/",
        BoardComponentListView.as_view(),
        name="board-components",
    ),
    path(
        "dashboards/<uuid:uuid>/components/<uuid:component_id>/",
        BoardComponentDetailView.as_view(),
        name="board-component-detail",
    ),
]
