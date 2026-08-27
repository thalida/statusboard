import secrets
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

from common.models import BaseModel

MAGIC_LINK_TTL = timedelta(minutes=15)


def _unusable_password():
    # Give every new row an unusable password, even outside `create_user`.
    return make_password(None)


class UserManager(BaseUserManager):
    def create_user(self, email, **extra):
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        """An admin is the one user who needs a password.

        The magic-link flow signs ordinary users in without one, so
        `create_user` marks every password unusable. Django's admin login
        form authenticates by password, so without this a superuser is
        created successfully and then cannot get in.
        """
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        user = self.create_user(email, **extra)
        if password:
            user.set_password(password)
            user.save(using=self._db, update_fields=["password"])
        return user


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, default=_unusable_password)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    last_active_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta(BaseModel.Meta):
        abstract = False

    def __str__(self):
        return self.email


class MagicLinkToken(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="magic_links")
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Set the expiry only on first save. A later save must not extend it.
        if not self.expires_at:
            self.expires_at = timezone.now() + MAGIC_LINK_TTL
        super().save(*args, **kwargs)

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now()
