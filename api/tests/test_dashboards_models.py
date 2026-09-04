import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from authentication.models import User
from dashboards.models import Dashboard, DashboardItem
from tests.factories import ComponentFactory


@pytest.mark.django_db
def test_a_user_gets_a_board_and_opens_it():
    user = User.objects.create(email="a@b.com")

    board = Dashboard.objects.get(owner=user)
    assert user.default_dashboard == board
    assert board.is_default


@pytest.mark.django_db
def test_a_user_cannot_hold_two_defaults():
    """It is one pointer, so there is no second one to hold.

    A flag on each board needed a rule saying only one may be set, and a
    rule can be broken. This cannot.
    """
    user = User.objects.create(email="a@b.com")
    first = user.default_dashboard
    second = Dashboard.objects.create(owner=user, name="Second")

    user.default_dashboard = second
    user.save(update_fields=["default_dashboard"])

    first.refresh_from_db()
    user.refresh_from_db()
    assert not first.is_default
    assert second.is_default
    assert user.default_dashboard == second


@pytest.mark.django_db
def test_one_owner_default_does_not_move_another_owner():
    mine = User.objects.create(email="a@b.com")
    theirs = User.objects.create(email="c@d.com")
    other = theirs.default_dashboard

    mine.default_dashboard = Dashboard.objects.create(owner=mine, name="Second")
    mine.save(update_fields=["default_dashboard"])

    theirs.refresh_from_db()
    assert theirs.default_dashboard == other


@pytest.mark.django_db
def test_a_component_is_tracked_once_per_dashboard():
    user = User.objects.create(email="a@b.com")
    board = Dashboard.objects.get(owner=user)
    component = ComponentFactory()
    DashboardItem.objects.create(dashboard=board, component=component)
    with pytest.raises(IntegrityError):
        DashboardItem.objects.create(dashboard=board, component=component)


@pytest.mark.django_db
def test_the_system_account_cannot_sign_in():
    system = User.objects.system()

    assert system.is_bot
    assert not system.is_active
    assert not system.has_usable_password()


@pytest.mark.django_db
def test_a_bot_reads_no_board():
    # The rule is the flag, not the one address, so a machine account
    # added later gets no board either.
    bot = User.objects.create(email="importer@statusboard.invalid", is_bot=True)

    assert not Dashboard.objects.filter(owner=bot).exists()


@pytest.mark.django_db
def test_the_system_account_reads_no_board():
    # It is nobody. A board for it would appear in the admin as a person's.
    system = User.objects.system()

    assert not Dashboard.objects.filter(owner=system).exists()


@pytest.mark.django_db
def test_the_system_account_is_one_account():
    assert User.objects.system() == User.objects.system()


@pytest.mark.django_db
def test_a_user_signs_their_own_default_board():
    user = User.objects.create(email="a@b.com")

    assert user.default_dashboard.created_by == user


@pytest.mark.django_db
def test_an_owner_keeps_their_last_board():
    # They read a board on sign-in. With none there is nothing to open.
    user = User.objects.create(email="a@b.com")
    only = Dashboard.objects.get(owner=user)

    with pytest.raises(ValidationError):
        only.delete()

    assert Dashboard.objects.filter(owner=user).exists()


@pytest.mark.django_db
def test_the_default_moves_on_when_its_board_goes():
    user = User.objects.create(email="a@b.com")
    first = user.default_dashboard
    second = Dashboard.objects.create(owner=user, name="Second")

    first.delete()

    user.refresh_from_db()
    assert user.default_dashboard == second


@pytest.mark.django_db
def test_an_owner_is_never_left_without_a_default():
    """There is no state where a person has boards and opens none.

    Clearing the last flag used to be the way in. A pointer has no
    cleared state that a board can be in.
    """
    user = User.objects.create(email="a@b.com")
    Dashboard.objects.create(owner=user, name="Second")

    user.refresh_from_db()
    assert user.default_dashboard is not None
    assert user.default_dashboard.owner == user


@pytest.mark.django_db
def test_closing_an_account_still_takes_its_boards():
    # The rule is on the model. Deleting a user is a bulk path and
    # never reaches it, which is what lets the account close.
    user = User.objects.create(email="a@b.com")

    user.delete()

    assert not Dashboard.objects.filter(owner_id=user.pk).exists()


@pytest.mark.django_db
def test_a_factory_user_and_a_tracked_one_never_collide():
    # `track` minted its own address from a counter that resets per
    # test. UserFactory's persists across the session, and email is
    # unique. The first test to call both would raise far from the cause.
    from tests.factories import UserFactory, track

    UserFactory.reset_sequence(0)
    UserFactory()
    track(ComponentFactory())

    assert User.objects.filter(email__startswith="watcher").count() == 2
