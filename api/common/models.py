import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    # Version 7, not 4. The first 48 bits are a millisecond timestamp, so
    # keys sort by creation and land at the end of the index instead of
    # scattering across it. Still a UUID: same column, same API, same
    # OpenAPI type. It publishes when a row was made, which nothing here
    # keeps secret; the one credential in the project is `token` on
    # MagicLinkToken, which is its own field.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # An audit trail, so nobody fills these in. The admin stamps them.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]
