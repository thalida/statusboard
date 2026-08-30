import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    # Version 7, not 4. The first 48 bits are a millisecond timestamp.
    # Keys sort by creation and land at the end of the index. Still a
    # UUID: same column, same API, same OpenAPI type.
    #
    # It publishes when a row was made. Nothing here keeps that secret.
    # The one credential is `token` on MagicLinkToken, its own field.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # An audit trail, so nobody fills these in. The admin stamps them.
    #
    # `related_name="+"` asks Django for no reverse accessor. Every
    # model here inherits both fields, so the default names collide on
    # User. The rest would be noise: `user.pollrun_set` reading as "runs
    # this person edited".
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
