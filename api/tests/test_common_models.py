import uuid

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
