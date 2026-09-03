"""`just reset` runs this, so a break here is a break in the reset."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.defaults import Environment
from authentication.management.commands import seed_dev
from catalog.models import Service
from dashboards.models import Dashboard, DashboardItem
from tests.factories import ComponentFactory, ServiceFactory, StatusPageFactory


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    """The admin `seed_admin` makes, which this command needs an owner from.

    A developer has these in .env.local, and that file is gitignored. So
    the suite passed here and failed on a machine that had never run
    `just env`.
    """
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "dev-only-password")


@pytest.fixture
def imports(monkeypatch):
    """Stand in for the fetch. The suite reaches no network.

    Each URL makes a service with an overall component, which is what
    the command tracks.
    """
    made = {}

    def fake(url):
        # Returns the one it already made, the way the real importer
        # does for a page already in the catalog.
        if url in made:
            return made[url], False
        service = ServiceFactory(name=url.rsplit("/", 1)[-1])
        StatusPageFactory(service=service)
        ComponentFactory(service=service, is_overall=True, name=service.name)
        made[url] = service
        return service, True

    monkeypatch.setattr(seed_dev, "import_from_url", fake)
    return made


@pytest.mark.django_db
def test_it_imports_the_catalog_and_tracks_one_of_it(imports):
    call_command("seed_dev")

    assert set(imports) == set(seed_dev.SERVICES)
    assert Service.objects.count() == len(seed_dev.SERVICES)
    tracked = [item.component.service for item in DashboardItem.objects.all()]
    assert [s.pk for s in tracked] == [imports[url].pk for url in seed_dev.TRACKED]


@pytest.mark.django_db
def test_the_rest_of_the_catalog_stays_untracked(imports):
    # Untracked is what makes "tracked" mean anything on the dashboard.
    call_command("seed_dev")

    from polling.models import Poller

    assert Poller.objects.active().count() == len(seed_dev.TRACKED)
    assert len(seed_dev.TRACKED) < len(seed_dev.SERVICES)


@pytest.mark.django_db
def test_it_tracks_the_rollup_not_a_leaf(imports):
    # It is the row a new user adds first, and tracking it is what makes
    # the service polled.
    call_command("seed_dev")

    assert all(item.component.is_overall for item in DashboardItem.objects.all())


@pytest.mark.django_db
def test_running_it_twice_changes_nothing(imports):
    call_command("seed_dev")
    before = (Service.objects.count(), DashboardItem.objects.count())

    call_command("seed_dev")

    assert (Service.objects.count(), DashboardItem.objects.count()) == before


@pytest.mark.django_db
@pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
def test_it_refuses_to_run_outside_development(environment, settings, imports):
    # A deployment must never grow rows because a command ran.
    settings.ENVIRONMENT = environment

    with pytest.raises(CommandError, match="development only"):
        call_command("seed_dev")

    assert Service.objects.count() == 0


@pytest.mark.django_db
def test_it_says_so_when_a_tracked_url_is_not_in_the_catalog(monkeypatch, imports):
    # The two lists are edited by hand, and one names the other.
    monkeypatch.setattr(seed_dev, "TRACKED", ["https://status.absent.test"])

    with pytest.raises(CommandError, match="not in SERVICES"):
        call_command("seed_dev")


@pytest.mark.django_db
def test_it_says_so_when_there_is_no_admin_to_own_a_board(monkeypatch, imports):
    monkeypatch.setattr(seed_dev, "call_command", lambda *a, **kw: None)

    with pytest.raises(CommandError, match="No admin"):
        call_command("seed_dev")


@pytest.mark.django_db
def test_it_says_so_when_the_admin_has_no_board(monkeypatch, imports):
    from django.contrib.auth import get_user_model

    owner = get_user_model().objects.create_superuser("admin@example.test")

    def strip_boards(*args, **kwargs):
        owner.default_dashboard = None
        owner.save(update_fields=["default_dashboard"])
        Dashboard.objects.filter(owner=owner).delete()

    monkeypatch.setattr(seed_dev, "call_command", strip_boards)

    with pytest.raises(CommandError, match="no board"):
        call_command("seed_dev")
