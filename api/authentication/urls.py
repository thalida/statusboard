from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from authentication.views import MagicLinkView, MeView, VerifyView

urlpatterns = [
    path("auth/magic-link/", MagicLinkView.as_view(), name="magic-link"),
    path("auth/verify/", VerifyView.as_view(), name="verify"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/logout/", TokenBlacklistView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
]
