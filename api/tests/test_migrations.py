"""The data migration that fills the ancestry table.

It runs once. A service nobody polls is never rebuilt, so what this
writes is what that service keeps.

The function is called directly, against the live app registry. It
reads `parent`, which the models still hold, so a historical registry
would answer the same.
"""

from importlib import import_module

import pytest

from catalog.models import ComponentAncestor
from tests.factories import ComponentFactory, ServiceFactory, ancestry

fill_from_parent = import_module(
    "catalog.migrations.0008_component_ancestor_table"
).fill_from_parent

pytestmark = pytest.mark.django_db


def backfill():
    """Run the migration against a table it has not seen."""
    from django.apps import apps

    ComponentAncestor.objects.all().delete()
    fill_from_parent(apps, None)


def test_the_backfill_writes_the_chain_of_every_component():
    # Nothing else fills the table on a service nobody polls. An empty
    # backfill leaves every such component with no descendants and no
    # breadcrumb, forever.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)

    backfill()

    assert ancestry(top) == []
    assert ancestry(middle) == [top.id]
    assert ancestry(leaf) == [top.id, middle.id]


def test_the_backfill_gives_a_row_whose_parent_went_no_ancestors():
    # `parent` is SET_NULL, so deleting a component makes its children
    # roots. Keeping the steps above the gap answers `?ancestor=` with a
    # tree nobody sits in. It also inflates the top row's count.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)
    middle.delete()

    backfill()

    leaf.refresh_from_db()
    assert ancestry(leaf) == []
    assert top.descendant_links.count() == 0


def test_the_backfill_stops_at_the_service_boundary():
    # Moving a component to another service leaves its old children
    # pointing across. A step there names a row the old service's lists
    # never hold.
    old = ServiceFactory()
    top = ComponentFactory(service=old)
    leaf = ComponentFactory(service=old, parent=top)
    top.service = ServiceFactory()
    top.save()

    backfill()

    assert ancestry(leaf) == []


def test_a_loop_in_the_parent_column_does_not_hang_the_backfill():
    # The column points at its own table, so bad data can make a cycle.
    # Without the guard the migration never ends, and the deploy that
    # runs it never finishes.
    from catalog.models import ServiceComponent

    service = ServiceFactory()
    first = ComponentFactory(service=service)
    second = ComponentFactory(service=service, parent=first)
    # `update` skips `clean`, which is the only thing refusing this.
    ServiceComponent.objects.filter(pk=first.pk).update(parent=second)

    backfill()

    assert ancestry(first) == [second.id]
    assert ancestry(second) == [first.id]
