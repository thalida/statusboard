from datetime import timedelta

import pytest
from django.utils import timezone

from polling.models import Poller, PollRun
from polling.tasks import (
    due_pollers,
    exception_name,
    next_interval_seconds,
    poll_service,
)
from tests.factories import PollerFactory, ServiceFactory, StatusPageFactory


@pytest.mark.django_db
def test_only_watched_services_are_due():
    # Poll only what someone tracks. Other polls have no reader.
    watched = PollerFactory(service=ServiceFactory(watcher_count=1))
    StatusPageFactory(service=watched.service)
    unwatched = PollerFactory(service=ServiceFactory(watcher_count=0))
    StatusPageFactory(service=unwatched.service)
    assert list(due_pollers()) == [watched]


@pytest.mark.django_db
def test_a_paused_poller_is_never_due():
    paused = PollerFactory(service=ServiceFactory(watcher_count=1), is_paused=True)
    StatusPageFactory(service=paused.service)
    assert list(due_pollers()) == []


@pytest.mark.django_db
def test_a_poller_inside_its_cooldown_is_not_due():
    cooling = PollerFactory(
        service=ServiceFactory(watcher_count=1),
        next_at=timezone.now() + timedelta(minutes=5),
    )
    StatusPageFactory(service=cooling.service)
    assert list(due_pollers()) == []


@pytest.mark.django_db
def test_two_boards_tracking_one_service_produce_one_poller():
    # The cooldown is on the service, not on a user or a board.
    service = ServiceFactory(watcher_count=200)
    StatusPageFactory(service=service)
    PollerFactory(service=service)
    assert Poller.objects.filter(service=service).count() == 1
    assert len(list(due_pollers())) == 1


def test_backoff_doubles_and_stops_at_the_ceiling():
    assert next_interval_seconds(base=300, failures=0, ceiling=3600) == 300
    assert next_interval_seconds(base=300, failures=1, ceiling=3600) == 600
    assert next_interval_seconds(base=300, failures=2, ceiling=3600) == 1200
    assert next_interval_seconds(base=300, failures=10, ceiling=3600) == 3600


@pytest.mark.django_db
def test_a_failed_poll_records_the_run_and_increments_the_counter(monkeypatch):
    poller = PollerFactory(service=ServiceFactory(watcher_count=1))
    StatusPageFactory(service=poller.service)

    class Boom:
        def __init__(self, *a, **kw): ...

        def fetch_status(self):
            raise RuntimeError("upstream is down")

    monkeypatch.setattr("polling.tasks.for_provider", lambda provider: Boom)
    poll_service(str(poller.service_id))

    poller.refresh_from_db()
    assert poller.consecutive_failure_count == 1
    run = PollRun.objects.get(poller=poller)
    assert run.ok is False
    assert "upstream is down" in run.error
    assert run.error_type == "RuntimeError"


@pytest.mark.django_db
def test_a_failed_poll_never_clobbers_the_last_known_value(monkeypatch):
    from status.choices import Severity, StatusSource
    from status.models import ComponentStatus
    from tests.factories import ComponentFactory

    poller = PollerFactory(service=ServiceFactory(watcher_count=1))
    StatusPageFactory(service=poller.service)
    component = ComponentFactory(service=poller.service)
    ComponentStatus.objects.create(
        component=component,
        severity=Severity.OPERATIONAL,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )

    class Boom:
        def __init__(self, *a, **kw): ...

        def fetch_status(self):
            raise RuntimeError("down")

    monkeypatch.setattr("polling.tasks.for_provider", lambda provider: Boom)
    poll_service(str(poller.service_id))

    still = ComponentStatus.objects.get(component=component, ended_at__isnull=True)
    assert still.severity == Severity.OPERATIONAL


@pytest.mark.django_db
def test_a_successful_poll_resets_the_failure_counter(monkeypatch):
    poller = PollerFactory(
        service=ServiceFactory(watcher_count=1), consecutive_failure_count=4
    )
    StatusPageFactory(service=poller.service)

    class Fine:
        def __init__(self, *a, **kw): ...

        def fetch_status(self):
            return []

        def fetch_incidents(self):
            return []

        def fetch_service_metadata(self):
            return {}

        def fetch_logo(self):
            return "https://cdn.example/logo.png"

    monkeypatch.setattr("polling.tasks.for_provider", lambda provider: Fine)
    poll_service(str(poller.service_id))

    poller.refresh_from_db()
    assert poller.consecutive_failure_count == 0
    assert poller.last_success_at is not None
    assert poller.next_at > timezone.now()


@pytest.mark.django_db
def test_every_service_gets_a_poller():
    # A service added anywhere but the import endpoint used to have none,
    # so it was never polled and never appeared as due.
    service = ServiceFactory()
    assert Poller.objects.filter(service=service).exists()


@pytest.mark.django_db
def test_a_service_with_no_status_page_is_not_due():
    # There is nothing to read. Enqueuing it would only fail.
    ServiceFactory(watcher_count=1)
    assert list(due_pollers()) == []


@pytest.mark.django_db
def test_polling_a_service_with_no_status_page_does_nothing(monkeypatch):
    # A PollRun needs the page's url and provider, so there is not even a
    # row to write. It must not raise: the admin offers "Poll now".
    service = ServiceFactory(watcher_count=1)
    monkeypatch.setattr(
        "polling.tasks.for_provider",
        lambda provider: pytest.fail("fetched with no page"),
    )
    poll_service(str(service.id))
    assert not PollRun.objects.filter(poller__service=service).exists()


@pytest.mark.django_db
def test_an_api_url_override_replaces_the_page_url(monkeypatch):
    # The escape hatch for a page whose API lives somewhere the adapter
    # would not reach by joining a path onto the page URL.
    poller = PollerFactory(service=ServiceFactory(watcher_count=1))
    StatusPageFactory(service=poller.service, api_url_override="https://api.elsewhere/")
    seen = {}

    class Recorder:
        def __init__(self, url, session=None):
            seen["url"] = url

        def fetch_status(self):
            return []

        def fetch_incidents(self):
            return []

        def fetch_service_metadata(self):
            return {}

    monkeypatch.setattr("polling.tasks.for_provider", lambda provider: Recorder)
    poll_service(str(poller.service_id))
    assert seen["url"] == "https://api.elsewhere/"


@pytest.mark.django_db
def test_a_poller_nobody_added_is_signed_by_the_system():
    """The signal adds it, so the author says the system, not nobody.

    A blank author reads the same as one that was lost.
    """
    from django.contrib.auth import get_user_model

    service = ServiceFactory()

    assert service.poller.created_by == get_user_model().objects.system()


def test_a_failure_is_named_by_the_deepest_library_exception():
    # Wrappers stack. The outermost says "the network" and the innermost
    # says "errno"; the one in between is the only one worth grouping by.
    class NameResolutionError(Exception):
        pass

    NameResolutionError.__module__ = "urllib3.exceptions"

    try:
        try:
            try:
                raise OSError("gaierror")
            except OSError as inner:
                raise NameResolutionError("no such host") from inner
        except NameResolutionError as middle:
            raise ConnectionError("max retries") from middle
    except ConnectionError as outer:
        assert exception_name(outer) == "NameResolutionError"


def test_a_failure_with_no_library_in_the_chain_keeps_its_own_name():
    assert exception_name(ValueError("plain")) == "ValueError"


@pytest.mark.django_db
def test_a_finished_failure_must_name_its_error():
    # An unnamed failure cannot be grouped, filtered or counted, so the
    # database refuses it rather than leaving one on the dashboard.
    from django.db import IntegrityError, transaction

    poller = PollerFactory(service=ServiceFactory(watcher_count=1))
    page = StatusPageFactory(service=poller.service)
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        PollRun.objects.create(
            poller=poller,
            url=page.url,
            provider=page.provider,
            started_at=now,
            finished_at=now,
            ok=False,
            error="something went wrong",
        )


@pytest.mark.django_db
def test_a_run_still_in_flight_has_nothing_to_name_yet():
    poller = PollerFactory(service=ServiceFactory(watcher_count=1))
    page = StatusPageFactory(service=poller.service)
    run = PollRun.objects.create(
        poller=poller,
        url=page.url,
        provider=page.provider,
        started_at=timezone.now(),
    )
    assert run.finished_at is None
    assert run.error_type == ""
