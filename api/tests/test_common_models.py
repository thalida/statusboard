import pytest
from django.db import models

from common.models import BaseModel


def test_base_model_is_abstract():
    assert BaseModel._meta.abstract is True


def test_base_model_orders_newest_first():
    assert list(BaseModel._meta.ordering) == ["-created_at"]


def test_primary_key_is_a_uuid_not_an_integer():
    # Version 7 leads with a millisecond timestamp, so a key lands at
    # the end of the index. Nothing needs a second column to sort by.
    pk = BaseModel._meta.get_field("id")
    assert isinstance(pk, models.UUIDField)
    assert pk.primary_key is True
    assert pk.default().version == 7


def test_audit_columns_exist_and_are_optional():
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


def test_a_column_with_two_defaults_declares_one_value():
    """`default` and `db_default` do different jobs, on the same column.

    Without `default` an unsaved instance holds a sentinel rather than
    the value. Without `db_default` the column carries no default, and
    a writer that predates it fails the insert.

    A field needs both. If the two ever disagree, a row Python makes
    and a row SQL makes differ on one column. Nothing would say so.
    """
    from django.apps import apps
    from django.db.models import NOT_PROVIDED

    both = {
        f"{model._meta.label}.{field.name}": (field.default, field.db_default)
        for model in apps.get_models()
        for field in model._meta.concrete_fields
        if field.default is not NOT_PROVIDED and field.db_default is not NOT_PROVIDED
    }
    # Nothing declaring both would make the check below vacuous.
    assert both
    disagreeing = {
        name: values for name, values in both.items() if values[0] != values[1]
    }
    assert not disagreeing, f"two defaults, two values: {disagreeing}"
