from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.emails import send_magic_link
from authentication.models import MagicLinkToken
from authentication.serializers import (
    MagicLinkRequestSerializer,
    MeSerializer,
    TokenPairSerializer,
    VerifyRequestSerializer,
)

User = get_user_model()


class MagicLinkView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=MagicLinkRequestSerializer,
        responses={
            202: OpenApiResponse(description="Sent, if the address can receive it."),
            429: OpenApiResponse(description="Too many requests."),
        },
    )
    def post(self, request):
        # Always create the user and send mail. An error here would reveal
        # that the email is unregistered.
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "email is required"}, status=400)
        user, _ = User.objects.get_or_create(email=email)
        link = MagicLinkToken.objects.create(user=user)
        send_magic_link(link)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=VerifyRequestSerializer,
        responses={
            200: TokenPairSerializer,
            400: OpenApiResponse(description="Invalid or expired token."),
        },
    )
    def post(self, request):
        link = MagicLinkToken.objects.filter(
            token=request.data.get("token") or ""
        ).first()
        if link is None or not link.is_usable:
            return Response({"detail": "invalid or expired token"}, status=400)
        link.used_at = timezone.now()
        link.save(update_fields=["used_at"])
        link.user.last_login = timezone.now()
        link.user.save(update_fields=["last_login"])
        refresh = RefreshToken.for_user(link.user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MeSerializer})
    def get(self, request):
        return Response(MeSerializer(request.user, context={"request": request}).data)

    @extend_schema(responses={204: OpenApiResponse(description="Account deleted.")})
    def delete(self, request):
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
