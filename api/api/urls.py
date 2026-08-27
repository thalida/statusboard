from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from common.views import ApiDocsView

urlpatterns = [
    # Above admin/ so the admin catch-all does not shadow it.
    path("admin/api-docs/", ApiDocsView.as_view(), name="api-docs"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/", include("common.urls")),
    path("api/", include("authentication.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("dashboards.urls")),
]
