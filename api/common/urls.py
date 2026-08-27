from django.urls import path

from common.views import MetaView

urlpatterns = [path("meta/", MetaView.as_view(), name="meta")]
