import pytest
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from common.ordering import MappedOrderingFilter
from tests.factories import ComponentFactory, ServiceFactory, track


def _view(ordering_fields, ordering_map):
    return type(
        "V", (), {"ordering_fields": ordering_fields, "ordering_map": ordering_map}
    )()


def test_a_related_path_ordering_does_not_reach_the_paginator():
    # CursorPagination asserts '__' not in ordering. The map keeps it flat.
    view = _view(["name"], {"status__severity": ["severity_now"]})
    out = MappedOrderingFilter().remove_invalid_fields(
        None, ["-status__severity"], view, None
    )
    assert out == ["-severity_now"]
    assert all("__" not in term for term in out)


def test_an_unmapped_unknown_value_is_refused():
    # Dropping it sorted the list by the default instead. The caller
    # asked for one order and read another, with nothing to say so.
    view = _view(["name"], {})
    with pytest.raises(ValidationError) as raised:
        MappedOrderingFilter().remove_invalid_fields(None, ["nonsense"], view, None)
    assert raised.value.detail == {"ordering": ["Unknown ordering: nonsense."]}


def test_reversing_a_key_that_names_its_own_directions_is_refused():
    # `-suggested` prefixed every mapped term and built `--is_featured`.
    # The ORM raised FieldError from there, which reached the caller as
    # a 500.
    view = _view(["name"], {"suggested": ["-is_featured", "name"]})
    with pytest.raises(ValidationError) as raised:
        MappedOrderingFilter().remove_invalid_fields(None, ["-suggested"], view, None)
    assert raised.value.detail == {"ordering": ["Cannot reverse: -suggested."]}


def test_a_value_that_is_not_a_field_expands_to_several():
    # `suggested` is not a column. It is an editorial order.
    view = _view(["name"], {"suggested": ["-is_featured", "-watcher_count"]})
    out = MappedOrderingFilter().remove_invalid_fields(None, ["suggested"], view, None)
    assert out == ["-is_featured", "-watcher_count"]


def test_a_plain_declared_field_passes_through():
    view = _view(["name"], {})
    assert MappedOrderingFilter().remove_invalid_fields(
        None, ["-name"], view, None
    ) == ["-name"]


def _component_list(client, authed, board):
    ComponentFactory(service=ServiceFactory(), is_overall=True)
    return client, reverse("component-list")


def _event_list(client, authed, board):
    return client, reverse("event-list")


def _board_components(client, authed, board):
    track(ComponentFactory(), user=board.owner)
    return authed, reverse("board-components", kwargs={"uuid": board.id})


# One builder per operation the contract gives an `ordering` parameter.
# A list added later and left out here would shrug again.
ORDERING_PROBES = {
    "/catalog/components/": _component_list,
    "/events/": _event_list,
    "/dashboards/{uuid}/components/": _board_components,
}


@pytest.mark.django_db
@pytest.mark.parametrize("path", sorted(ORDERING_PROBES))
def test_an_unknown_ordering_is_refused(path, client, authenticated_client, board):
    # `?fields=` refuses an unknown name and `?ordering=` shrugged. One
    # parameter that answers 400 and one that does not is two contracts.
    caller, url = ORDERING_PROBES[path](client, authenticated_client, board)
    response = caller.get(url, {"ordering": "nonsense"})
    assert response.status_code == 400, f"GET {path} answered {response.status_code}"
    assert response.json() == {"ordering": ["Unknown ordering: nonsense."]}


@pytest.mark.django_db
def test_reversing_suggested_is_a_400_not_a_500(client, authenticated_client, board):
    # `suggested` is four terms, two of them already descending. The
    # prefix built `--is_featured` and the ORM raised on it.
    caller, url = _component_list(client, authenticated_client, board)
    response = caller.get(url, {"ordering": "-suggested"})
    assert response.status_code == 400
    assert response.json() == {"ordering": ["Cannot reverse: -suggested."]}
