import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from status.choices import EVENT_PHASES_BY_KIND, EventKind, Severity


def test_lower_severity_is_worse():
    assert Severity.MAJOR_OUTAGE == 0
    assert Severity.PARTIAL_OUTAGE == 1
    assert Severity.DEGRADED == 2
    assert Severity.UNKNOWN == 3
    assert Severity.MAINTENANCE == 4
    assert Severity.OPERATIONAL == 5


def test_unknown_sorts_with_the_problems_not_the_healthy():
    # A service we cannot reach belongs with the problems.
    # This makes `severity <= 3` mean "needs attention".
    needs_attention = [s for s in Severity if s <= 3]
    assert Severity.UNKNOWN in needs_attention
    assert Severity.MAINTENANCE not in needs_attention
    assert Severity.OPERATIONAL not in needs_attention


def test_every_event_kind_has_a_phase_set():
    assert set(EVENT_PHASES_BY_KIND) == {EventKind.INCIDENT, EventKind.MAINTENANCE}


@pytest.mark.django_db
def test_meta_publishes_every_enum():
    body = APIClient().get(reverse("meta")).json()
    assert set(body["enums"]) == {
        "severity",
        "status_source",
        "status_page_provider",
        "event_kind",
        "event_phase",
    }
    assert body["enums"]["severity"]["0"] == "Major outage"
    assert body["enums"]["severity"]["5"] == "Operational"
    # event_phase is keyed by kind, because the valid set depends on it
    assert set(body["enums"]["event_phase"]) == {"incident", "maintenance"}
    assert "investigating" in body["enums"]["event_phase"]["incident"]
    assert "scheduled" in body["enums"]["event_phase"]["maintenance"]


@pytest.mark.django_db
def test_meta_publishes_the_deployment_defaults():
    body = APIClient().get(reverse("meta")).json()
    assert body["poll_interval_seconds"] == 300
    assert body["poll_cooldown_seconds"] == 60
    assert body["default_page_size"] == 50
    assert body["max_page_size"] == 200


def test_debug_allows_local_hosts_and_nothing_else():
    # A wildcard accepts any Host header, and the machine running the dev
    # server is usually also on a network.
    from django.conf import settings

    assert "*" not in settings.ALLOWED_HOSTS
    assert set(settings.LOCAL_HOSTS) <= set(settings.ALLOWED_HOSTS)


def test_an_unset_allowed_hosts_leaves_no_blank_entry():
    # `"".split(",")` is `[""]`, which looks configured and matches
    # nothing. Django refuses an empty list out loud instead.
    from django.conf import settings

    assert "" not in settings.ALLOWED_HOSTS


def test_one_page_size_serves_the_paginator_the_api_and_meta():
    # DRF held its own 50 next to DEFAULT_PAGE_SIZE. `/meta` publishes
    # the second one, so the two could disagree and nothing would say so.
    from django.conf import settings

    from common.pagination import EnvelopePagination

    assert settings.REST_FRAMEWORK["PAGE_SIZE"] == settings.DEFAULT_PAGE_SIZE
    assert EnvelopePagination.page_size == settings.DEFAULT_PAGE_SIZE
    assert EnvelopePagination.max_page_size == settings.MAX_PAGE_SIZE


def test_the_project_tunables_come_from_one_module():
    from django.conf import settings

    from api import defaults

    for name in (
        "DEFAULT_PAGE_SIZE",
        "MAX_PAGE_SIZE",
        "POLL_INTERVAL_SECONDS",
        "POLL_COOLDOWN_SECONDS",
        "POLL_MAX_INTERVAL_SECONDS",
    ):
        assert getattr(settings, name) == getattr(defaults, name)


def test_the_environment_is_one_of_a_known_set():
    from django.conf import settings

    from api.defaults import Environment

    assert isinstance(settings.ENVIRONMENT, Environment)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("local", "local"),
        ("  Production  ", "production"),
        ("STAGING", "staging"),
        ("", "local"),
        (None, "local"),
    ],
)
def test_the_environment_is_normalised(given, expected):
    # Case and stray whitespace are the shape a typo usually takes.
    from api.defaults import Environment

    assert Environment.parse(given) is Environment(expected)


def test_an_unknown_environment_is_refused():
    # Falling back would colour a production banner as an unknown
    # deployment and let the seeding commands run there.
    from api.defaults import Environment

    with pytest.raises(ValueError, match="Expected one of"):
        Environment.parse("prod")
