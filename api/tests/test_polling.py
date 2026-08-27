from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import Poller
from status.models import PollRun
from status.tasks import due_pollers, next_interval_seconds, poll_service
from tests.factories import PollerFactory, ServiceFactory, StatusPageFactory


@pytest.mark.django_db
def test_only_watched_services_are_due():
    # Poll only what someone tracks. Other polls have no reader.
    watched = PollerFactory(service=ServiceFactory(watcher_count=1))
    PollerFactory(service=ServiceFactory(watcher_count=0))
    assert list(due_pollers()) == [watched]


@pytest.mark.django_db
def test_a_paused_poller_is_never_due():
    PollerFactory(service=ServiceFactory(watcher_count=1), is_paused=True)
    assert list(due_pollers()) == []


@pytest.mark.django_db
def test_a_poller_inside_its_cooldown_is_not_due():
    PollerFactory(
        service=ServiceFactory(watcher_count=1),
        next_at=timezone.now() + timedelta(minutes=5),
    )
    assert list(due_pollers()) == []


@pytest.mark.django_db
def test_two_boards_tracking_one_service_produce_one_poller():
    # The cooldown is on the service, not on a user or a board.
    service = ServiceFactory(watcher_count=200)
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

    monkeypatch.setattr("status.tasks.detect", lambda url: Boom)
    poll_service(str(poller.service_id))

    poller.refresh_from_db()
    assert poller.consecutive_failure_count == 1
    run = PollRun.objects.get(poller=poller)
    assert run.ok is False
    assert "upstream is down" in run.error


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

    monkeypatch.setattr("status.tasks.detect", lambda url: Boom)
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

    monkeypatch.setattr("status.tasks.detect", lambda url: Fine)
    poll_service(str(poller.service_id))

    poller.refresh_from_db()
    assert poller.consecutive_failure_count == 0
    assert poller.last_success_at is not None
    assert poller.next_at > timezone.now()
