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
    assert pk.default is uuid.uuid4


def test_audit_columns_exist_and_are_optional():
    for name in ("created_at", "updated_at"):
        assert BaseModel._meta.get_field(name) is not None
    for name in ("created_by", "updated_by"):
        field = BaseModel._meta.get_field(name)
        assert field.null is True, (
            f"{name} must be null — the poller writes rows with no user"
        )
