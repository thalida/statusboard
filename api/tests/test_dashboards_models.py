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
def test_an_owner_has_at_most_one_default():
    user = User.objects.create(email="a@b.com")
    with pytest.raises(IntegrityError):
        Dashboard.objects.create(owner=user, name="Second", is_default=True)


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
