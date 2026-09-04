"""The archived rule, against every reader that serves components.

A provider stops publishing a component. The row is archived rather
than deleted, because somebody may be tracking it.
`ServiceComponentQuerySet.visible` is the one definition of which rows
a caller is served.

Three readers have forgotten to call it: the Affects badge,
`tracked_component_count` and the board write. Each was caught by hand
in review. Remembering has failed three times, so the suite asks
instead.

The last test derives its list of paths from the contract. So it fails
on an operation that serves a component and has no probe. It says
nothing about a new reader on a path a probe already covers. Another
query parameter, or a nested component on a schema that path returns,
adds no path and trips nothing.
"""

from pathlib import Path
from unittest import mock

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from dashboards.models import DashboardItem
from status.choices import EventKind, IncidentPhase
from status.models import ServiceEvent
from tests.conftest import jwt_client
from tests.factories import ComponentFactory, ServiceFactory, StatusPageFactory

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"

pytestmark = pytest.mark.django_db


def archived(service=None, **fields):
    """A component the provider stopped publishing."""
    row = ComponentFactory(service=service or ServiceFactory(), **fields)
    row.is_archived = True
    row.save(update_fields=["is_archived"])
    return row


def signed_in():
    return jwt_client(User.objects.create(email="archived-probe@example.test"))


def incident(service):
    return ServiceEvent.objects.create(
        service=service,
        external_id="probe",
        kind=EventKind.INCIDENT,
        title="x",
        phase=IncidentPhase.DETECTED,
        starts_at=timezone.now(),
    )


# Each probe archives one component and returns what a caller can still
# see of it. Anything truthy is a leak.


def component_list():
    gone = archived()
    body = APIClient().get(reverse("component-list"), {"service": gone.service.slug})
    return body.json()["results"] or body.json()["aggregates"]["total"]


def descendants_of_a_component():
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    archived(service=service, parent=top)
    url = reverse("component-list")
    return APIClient().get(url, {"ancestor": str(top.id)}).json()["results"]


def an_events_affected_list():
    gone = archived()
    event = incident(gone.service)
    event.affected_components.add(gone)
    url = reverse("component-list")
    return APIClient().get(url, {"event": str(event.id)}).json()["results"]


def component_detail():
    gone = archived()
    response = APIClient().get(reverse("component-detail", args=[gone.id]))
    return response.status_code != 404


def a_components_path():
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = archived(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)
    body = APIClient().get(reverse("component-detail", args=[leaf.id])).json()
    return [node for node in body["path"] if node["id"] == str(middle.id)]


def a_components_descendant_count():
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    archived(service=service, parent=top)
    body = APIClient().get(reverse("component-detail", args=[top.id])).json()
    return body["descendant_count"]


def a_services_component_count():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    archived(service=service)
    url = reverse("service-detail", kwargs={"slug": service.slug})
    return APIClient().get(url).json()["component_count"]


def a_services_tracked_count():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    gone = archived(service=service)
    caller = signed_in()
    DashboardItem.objects.create(
        dashboard=User.objects.get(
            email="archived-probe@example.test"
        ).default_dashboard,
        component=gone,
    )
    url = reverse("service-detail", kwargs={"slug": service.slug})
    return caller.get(url).json()["tracked_component_count"]


def an_imported_services_counts():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    archived(service=service)
    with (
        mock.patch("polling.fetch.check", lambda url: url),
        mock.patch(
            "catalog.views.imports.import_from_url", return_value=(service, False)
        ),
    ):
        body = APIClient().post(
            reverse("catalog-import"),
            {"status_page_url": "https://status.example.com/"},
            format="json",
        )
    return body.json()["component_count"]


def the_board_list():
    caller = signed_in()
    board = User.objects.get(email="archived-probe@example.test").default_dashboard
    gone = archived()
    DashboardItem.objects.create(dashboard=board, component=gone)
    url = reverse("board-components", kwargs={"uuid": board.id})
    body = caller.get(url).json()
    return body["results"] or body["aggregates"]["total"]


def the_track_write():
    caller = signed_in()
    board = User.objects.get(email="archived-probe@example.test").default_dashboard
    gone = archived()
    url = reverse("board-components", kwargs={"uuid": board.id})
    response = caller.post(url, {"component_id": str(gone.id)}, format="json")
    return response.status_code != 404


def the_affects_badge():
    gone = archived()
    event = incident(gone.service)
    event.affected_components.add(gone)
    url = reverse("event-detail", kwargs={"uuid": event.id})
    return APIClient().get(url).json()["affected_count"]


# One entry per reader, against the contract path it answers on. The
# path is what the coverage check below reads.
ARCHIVED_PROBES = {
    "the component list": ("/catalog/components/", component_list),
    "a component's descendants": ("/catalog/components/", descendants_of_a_component),
    "an event's affected list": ("/catalog/components/", an_events_affected_list),
    "the component detail": ("/catalog/components/{uuid}/", component_detail),
    "a component's path": ("/catalog/components/{uuid}/", a_components_path),
    "a component's descendant count": (
        "/catalog/components/{uuid}/",
        a_components_descendant_count,
    ),
    "a service's component count": (
        "/catalog/services/{slug}/",
        a_services_component_count,
    ),
    "a service's tracked count": (
        "/catalog/services/{slug}/",
        a_services_tracked_count,
    ),
    "an imported service's counts": ("/catalog/import/", an_imported_services_counts),
    "the board list": ("/dashboards/{uuid}/components/", the_board_list),
    "the track write": ("/dashboards/{uuid}/components/", the_track_write),
    "the Affects badge": ("/events/{uuid}/", the_affects_badge),
}


@pytest.mark.parametrize("reader", sorted(ARCHIVED_PROBES))
def test_no_reader_serves_an_archived_component(reader):
    # The one exception is `Service.overall_component`. A service whose
    # rollup is archived still needs a status in its header, and
    # `test_catalog_api` covers that.
    _path, probe = ARCHIVED_PROBES[reader]
    leaked = probe()
    assert not leaked, f"{reader} served an archived component: {leaked}"


def _reachable(node, schemas, found=None):
    """Every schema an operation can produce, following each `$ref`."""
    found = set() if found is None else found
    if isinstance(node, list):
        for item in node:
            _reachable(item, schemas, found)
        return found
    if not isinstance(node, dict):
        return found
    for key, value in node.items():
        if key == "$ref" and value.startswith("#/components/schemas/"):
            name = value.rsplit("/", 1)[1]
            if name not in found:
                found.add(name)
                _reachable(schemas.get(name, {}), schemas, found)
        else:
            _reachable(value, schemas, found)
    return found


def test_the_probes_cover_every_operation_that_can_serve_a_component():
    # A reader added later that forgets `visible()` serves a row the
    # provider stopped publishing, and nothing says so. This fails by
    # path, the way the `?fields=` probes do.
    contract = yaml.safe_load(CONTRACT.read_text())
    schemas = contract["components"]["schemas"]
    serves = {
        path
        for path, operations in contract["paths"].items()
        for operation in operations.values()
        if "Component" in _reachable(operation.get("responses", {}), schemas)
    }
    probed = {path for path, _probe in ARCHIVED_PROBES.values()}
    assert not serves - probed, (
        f"serves components, unprobed: {sorted(serves - probed)}"
    )
