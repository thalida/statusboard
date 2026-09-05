from django.urls import path

from status.views import EventDetailView, EventListView, EventUpdateListView

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
    path("events/<uuid:uuid>/", EventDetailView.as_view(), name="event-detail"),
    path(
        "events/<uuid:uuid>/updates/",
        EventUpdateListView.as_view(),
        name="event-updates",
    ),
]
