import pytest
from django.db.utils import IntegrityError

from authentication.models import User
from dashboards.models import Dashboard, DashboardItem
from tests.factories import ComponentFactory


@pytest.mark.django_db
def test_a_user_gets_a_default_dashboard_on_creation():
    user = User.objects.create(email="a@b.com")
    assert Dashboard.objects.filter(owner=user, is_default=True).count() == 1


@pytest.mark.django_db
def test_a_new_default_stands_down_the_old_one():
    user = User.objects.create(email="a@b.com")
    first = Dashboard.objects.get(owner=user, is_default=True)

    second = Dashboard.objects.create(owner=user, name="Second", is_default=True)

    first.refresh_from_db()
    assert not first.is_default
    assert second.is_default
    assert Dashboard.objects.filter(owner=user, is_default=True).count() == 1


@pytest.mark.django_db
def test_one_owner_default_does_not_stand_down_another_owner():
    mine = User.objects.create(email="a@b.com")
    theirs = User.objects.create(email="c@d.com")
    other = Dashboard.objects.get(owner=theirs, is_default=True)

    Dashboard.objects.create(owner=mine, name="Second", is_default=True)

    other.refresh_from_db()
    assert other.is_default


@pytest.mark.django_db
def test_two_owners_may_each_have_a_default():
    User.objects.create(email="a@b.com")
    User.objects.create(email="c@d.com")
    assert Dashboard.objects.filter(is_default=True).count() == 2


@pytest.mark.django_db
def test_a_component_is_tracked_once_per_dashboard():
    user = User.objects.create(email="a@b.com")
    board = Dashboard.objects.get(owner=user)
    component = ComponentFactory()
    DashboardItem.objects.create(dashboard=board, component=component)
    with pytest.raises(IntegrityError):
        DashboardItem.objects.create(dashboard=board, component=component)


@pytest.mark.django_db
def test_an_item_carries_no_position():
    # Order is a query, not a column. A stored position needs a rewrite on every insert.
    assert not hasattr(DashboardItem, "position")
