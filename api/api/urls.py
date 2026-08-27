from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from common.views import ApiDocsView

# This service is the API. It gets its own subdomain, so the endpoints sit
# at the root rather than behind /api/. That is also what docs/api/openapi.yaml
# has always documented.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("docs/", ApiDocsView.as_view(), name="api-docs"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("", include("common.urls")),
    path("", include("authentication.urls")),
    path("", include("catalog.urls")),
    path("", include("dashboards.urls")),
]
