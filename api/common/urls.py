from django.urls import path

from common.views import HealthView, MetaView

urlpatterns = [
    path("meta/", MetaView.as_view(), name="meta"),
    path("health/", HealthView.as_view(), name="health"),
]
