from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("common.urls")),
    path("api/", include("authentication.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("dashboards.urls")),
]
