import uuid

import pytest
from django.db import models

from common.models import BaseModel


def test_base_model_is_abstract():
    assert BaseModel._meta.abstract is True


def test_base_model_orders_newest_first():
    assert BaseModel._meta.ordering == ["-created_at"]


def test_primary_key_is_a_uuid_not_an_integer():
    pk = BaseModel._meta.get_field("id")
    assert isinstance(pk, models.UUIDField)
    assert pk.primary_key is True
    assert pk.default is uuid.uuid7


def test_keys_sort_by_the_order_they_were_made():
    # Version 7 leads with a millisecond timestamp, so a key lands at the
    # end of the index rather than in the middle of it.
    keys = [uuid.uuid7() for _ in range(50)]
    assert all(key.version == 7 for key in keys)
    assert keys == sorted(keys)


def test_audit_columns_exist_and_are_optional():
    for name in ("created_at", "updated_at"):
        assert BaseModel._meta.get_field(name) is not None
    for name in ("created_by", "updated_by"):
        field = BaseModel._meta.get_field(name)
        assert field.null is True, (
            f"{name} must be null — the poller writes rows with no user"
        )


@pytest.mark.django_db
def test_the_system_account_exists_before_anything_writes():
    # A migration makes it, so a fresh database has an author to name
    # before the first import or signal runs.
    from django.contrib.auth import get_user_model

    from api.defaults import SYSTEM_EMAIL

    account = get_user_model().objects.system()
    assert account.email == SYSTEM_EMAIL
    assert account.is_bot is True
    assert account.is_active is False
    # It signed itself, so no row the system wrote is left unsigned.
    assert account.created_by_id == account.pk
