import secrets
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from common.models import BaseModel

MAGIC_LINK_TTL = timedelta(minutes=15)


def _unusable_password():
    # Give every new row an unusable password, even outside `create_user`.
    return make_password(None)


# The domain is reserved by RFC 2606, so no mail can leave for it and no
# person can ever hold the address.
SYSTEM_EMAIL = "system@statusboard.invalid"


class UserManager(BaseUserManager):
    def system(self):
        """The account the system writes as.

        Rows the importer and the signals create have an author too, and
        a blank one reads the same as one that was lost. This gives them
        a name and a time. The account cannot sign in: it is not active,
        the password is unusable, and no link can reach the address.

        A row written by a poll carries its run instead. The run says
        which request read the page, which is more than a name.
        """
        user, _ = self.get_or_create(
            email=SYSTEM_EMAIL,
            defaults={"is_active": False, "is_bot": True},
        )
        return user

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
    is_bot = models.BooleanField(
        verbose_name="Bot",
        default=False,
        help_text="A machine account. It signs rows, it never signs in.",
    )
    last_active_at = models.DateTimeField(
        verbose_name="Last active", null=True, blank=True
    )
    # The board they open on sign-in. One pointer, so there is no way to
    # hold two defaults or none. Null only while the first board is being
    # made, which `save` does immediately below.
    #
    # SET_NULL rather than CASCADE: deleting a board must not delete the
    # person who read it. `Dashboard.delete` moves this on instead.
    default_dashboard = models.ForeignKey(
        "dashboards.Dashboard",
        verbose_name="Default board",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    def clean(self):
        """A person opens one of their own boards, not somebody else's.

        The column cannot say whose board it points at, so nothing stops
        it naming another owner's. That would show one person another
        person's board on sign-in.
        """
        super().clean()
        board = self.default_dashboard
        if board is not None and board.owner_id != self.pk:
            raise ValidationError(
                {"default_dashboard": "That board belongs to somebody else."}
            )

    def save(self, *args, **kwargs):
        """Give a new user their board, and open it by default.

        Imported here rather than at module scope: authentication is the
        lower layer, and a top-level import would tie it to dashboards for
        every reader of this file.
        """
        creating = self._state.adding
        super().save(*args, **kwargs)
        # A bot is nobody, so it reads no board.
        if creating and not self.is_bot:
            from dashboards.models import Dashboard

            board = Dashboard.objects.create(
                owner=self, created_by=self, updated_by=self
            )
            self.default_dashboard = board
            super().save(update_fields=["default_dashboard"])

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
    expires_at = models.DateTimeField(verbose_name="Expires")
    used_at = models.DateTimeField(verbose_name="Used", null=True, blank=True)

    def save(self, *args, **kwargs):
        # Set the expiry only on first save. A later save must not extend it.
        if not self.expires_at:
            self.expires_at = timezone.now() + MAGIC_LINK_TTL
        super().save(*args, **kwargs)

    def __str__(self):
        # Never the token itself. It is a credential, and a changelist is
        # read over shoulders and pasted into tickets.
        return f"{self.user} — {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now()
