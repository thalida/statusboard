from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from common.views import ApiDocsView

# This service is the API. It gets its own subdomain, so the endpoints sit
# at the root rather than behind /api/. That is also what docs/api/openapi.yaml
# has always documented.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # The root is the docs. Exact-match "", so /meta/ and the rest
    # still reach the includes below.
    path("", ApiDocsView.as_view(), name="api-docs"),
    path("", include("common.urls")),
    path("", include("authentication.urls")),
    path("", include("catalog.urls")),
    path("", include("dashboards.urls")),
    path("", include("status.urls")),
]
