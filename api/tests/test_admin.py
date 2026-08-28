import pytest
from django.contrib import admin
from django.urls import reverse

from authentication.models import User


@pytest.fixture
def staff_client(client):
    client.force_login(
        User.objects.create_superuser("admin@example.com", password="admin-only")
    )
    return client


def service_form_data(staff_client, **fields):
    """The service add form, with a management form per inline.

    The prefixes are read off the rendered page rather than derived. One
    of the inlines is a nonrelated one with no foreign key to work back
    from, and a browser posts exactly what the page asks for.
    """
    import re

    body = staff_client.get(reverse("admin:catalog_service_add")).content.decode()
    data = {
        "name": "",
        "slug": "",
        "description": "",
        "logo": "",
        "homepage_url": "",
        **fields,
    }
    for prefix in set(re.findall(r'name="([\w-]+)-TOTAL_FORMS"', body)):
        for key in ("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"):
            data[f"{prefix}-{key}"] = "0"
    return data


@pytest.mark.django_db
def test_the_dashboard_leads_with_poller_health(staff_client):
    # The landing page answers "is polling healthy?". A stalled poller
    # shows every board a stale green, which is worse than showing nothing.
    body = staff_client.get(reverse("admin:index")).content.decode()
    for card in (
        "Services tracked",
        "Pollers in backoff",
        "Poll success",
        "Oldest successful poll",
    ):
        assert card in body, f"{card} missing from the dashboard"


@pytest.mark.django_db
def test_the_environment_is_named_on_every_page(staff_client):
    # Acting on production believing it is local is the mistake worth
    # making loud.
    assert "Local" in staff_client.get(reverse("admin:index")).content.decode()


@pytest.mark.django_db
def test_the_brand_marks_are_wired(staff_client):
    body = staff_client.get(reverse("admin:index")).content.decode()
    assert "statusboard/logo-light.svg" in body
    assert "statusboard/favicon.svg" in body


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model",
    sorted(admin.site._registry, key=lambda m: m._meta.label),
    ids=lambda m: m._meta.label,
)
def test_every_registered_changelist_renders(staff_client, model):
    # Filters, @display callables and annotations only fail when rendered.
    opts = model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
    assert staff_client.get(url).status_code == 200


@pytest.mark.django_db
def test_a_service_can_be_added_from_a_related_popup(staff_client):
    # The autocomplete on a component offers "add another". A popup that
    # cannot save leaves you retyping the component form.
    from catalog.models import Service

    url = reverse("admin:catalog_service_add") + "?_to_field=id&_popup=1"
    assert staff_client.get(url).status_code == 200
    staff_client.post(
        url, service_form_data(staff_client, slug="from-popup", name="From popup")
    )
    assert Service.objects.filter(slug="from-popup").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model",
    sorted(admin.site._registry, key=lambda m: m._meta.label),
    ids=lambda m: m._meta.label,
)
def test_every_add_form_renders(staff_client, model):
    # Inlines, readonly fields and widgets only fail on the change form.
    # The changelist test above never touches them.
    opts = model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_add")
    assert staff_client.get(url).status_code in (200, 403)


# Written by apply_fetch and poll_service, never by hand.
POLLER_WRITTEN = [
    "status.ComponentStatus",
    "status.ServiceEvent",
    "status.EventUpdate",
    "polling.PollRun",
]


@pytest.mark.django_db
@pytest.mark.parametrize("label", POLLER_WRITTEN)
def test_poller_written_tables_are_not_editable(staff_client, settings, label):
    # A hand-written row invents history the API serves, or trips the
    # one-open-status constraint, and the next poll overwrites it anyway.
    # Pinned, not read from the environment: a developer seeding a local
    # database must not turn this assertion off.
    settings.ADMIN_EDITABLE_POLLER_DATA = False
    model = next(m for m in admin.site._registry if m._meta.label == label)
    site_admin = admin.site._registry[model]
    request = staff_client.request().wsgi_request
    assert not site_admin.has_add_permission(request)
    assert not site_admin.has_change_permission(request)
    assert not site_admin.has_delete_permission(request)


@pytest.mark.django_db
@pytest.mark.parametrize("label", POLLER_WRITTEN)
def test_the_seeding_flag_lifts_the_lock(staff_client, settings, label):
    # For filling a local database by hand. Off unless .env.local sets it,
    # so it cannot reach a deployment.
    settings.ADMIN_EDITABLE_POLLER_DATA = True
    model = next(m for m in admin.site._registry if m._meta.label == label)
    site_admin = admin.site._registry[model]
    request = staff_client.request().wsgi_request
    assert site_admin.has_add_permission(request)
    assert site_admin.has_change_permission(request)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "label", ["catalog.Service", "catalog.StatusPage", "polling.Poller"]
)
def test_the_admin_tunable_tables_stay_editable(staff_client, label):
    # A Poller's interval and pause flag are meant to be changed here.
    model = next(m for m in admin.site._registry if m._meta.label == label)
    site_admin = admin.site._registry[model]
    request = staff_client.request().wsgi_request
    assert site_admin.has_change_permission(request)


@pytest.mark.django_db
def test_the_admin_stamps_who_created_a_row(staff_client):
    # The fields are not editable, so nothing else can set them. Left
    # alone they stayed null forever: an audit trail recording nothing.
    from catalog.models import Service

    staff_client.post(
        reverse("admin:catalog_service_add"),
        service_form_data(staff_client, name="Stamped"),
    )
    service = Service.objects.get(name="Stamped")
    assert service.created_by.email == "admin@example.com"
    assert service.updated_by.email == "admin@example.com"


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["created_by", "updated_by", "watcher_count"])
def test_derived_fields_are_not_on_the_form(staff_client, field):
    # watcher_count decides what gets polled, so a hand edit would
    # silently start or stop polling a service.
    body = staff_client.get(reverse("admin:catalog_service_add")).content.decode()
    assert f'name="{field}"' not in body


@pytest.mark.django_db
def test_the_changelist_offers_an_import_button(staff_client):
    body = staff_client.get(
        reverse("admin:catalog_service_changelist")
    ).content.decode()
    assert "Import from URL" in body


@pytest.mark.django_db
def test_importing_from_the_admin_creates_the_service(staff_client, monkeypatch):
    from catalog.models import Service

    monkeypatch.setattr(
        "catalog.models.ServiceManager.import_from_url",
        lambda self, url: (Service.objects.create(name="Imported"), True),
    )
    response = staff_client.post(
        "/admin/catalog/service/import-from-url/",
        {"status_page_url": "https://status.example.com/", "_form_submitted": "1"},
    )
    assert response.status_code == 302
    assert Service.objects.filter(name="Imported").exists()


@pytest.mark.django_db
def test_an_unreadable_page_is_reported_not_a_500(staff_client, monkeypatch):
    # The URL came from a person pasting a stranger's page. Anything can
    # come back from it.
    def boom(self, url):
        raise ValueError("not a status page")

    monkeypatch.setattr("catalog.models.ServiceManager.import_from_url", boom)
    response = staff_client.post(
        "/admin/catalog/service/import-from-url/",
        {"status_page_url": "https://nope.example.com/", "_form_submitted": "1"},
        follow=True,
    )
    assert response.status_code == 200
    assert "could not be read" in response.content.decode()


@pytest.mark.django_db
def test_events_can_be_filtered_by_phase(staff_client):
    """Phase carries no choices on the field, so its options are built.

    An incident and a maintenance window move through different phases,
    which is why a plain ChoicesDropdownFilter cannot do this.
    """
    from django.utils import timezone

    from status.choices import EventKind, IncidentPhase, MaintenancePhase
    from status.models import ServiceEvent
    from tests.factories import ServiceFactory

    service = ServiceFactory()
    for external_id, kind, phase in [
        ("1", EventKind.INCIDENT, IncidentPhase.RESOLVED),
        ("2", EventKind.INCIDENT, IncidentPhase.INVESTIGATING),
        ("3", EventKind.MAINTENANCE, MaintenancePhase.SCHEDULED),
    ]:
        ServiceEvent.objects.create(
            service=service,
            external_id=external_id,
            kind=kind,
            title=external_id,
            phase=phase,
            starts_at=timezone.now(),
        )

    url = reverse("admin:status_serviceevent_changelist")
    body = staff_client.get(url).content.decode()
    assert "Incident: Resolved" in body
    assert "Maintenance: Scheduled" in body

    response = staff_client.get(url, {"phase": IncidentPhase.RESOLVED})
    assert list(response.context["cl"].queryset) == [
        ServiceEvent.objects.get(external_id="1")
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "admin:catalog_service_changelist",
        "admin:catalog_servicecomponent_changelist",
        "admin:status_serviceevent_changelist",
        "admin:status_componentstatus_changelist",
        "admin:polling_poller_changelist",
        "admin:polling_pollrun_changelist",
    ],
)
def test_every_table_links_somewhere(staff_client, url_name):
    """A table is a place you arrive from somewhere else.

    Each row carries a link to the record it belongs to, so reaching a
    service's components no longer means filtering a list by hand.
    """
    import re

    from django.utils import timezone

    from catalog.models import Service
    from polling.models import PollRun
    from status.choices import EventKind, IncidentPhase, Severity, StatusSource
    from status.models import ComponentStatus, ServiceEvent
    from tests.factories import ComponentFactory, ServiceFactory, StatusPageFactory

    service = ServiceFactory()
    StatusPageFactory(service=service)
    component = ComponentFactory(service=service)
    run = PollRun.objects.create(
        poller=service.poller,
        url="https://status.example.com",
        provider="statuspage",
        started_at=timezone.now(),
    )
    ComponentStatus.objects.create(
        component=component,
        severity=Severity.OPERATIONAL,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
        poll_run=run,
    )
    ServiceEvent.objects.create(
        service=service,
        external_id="1",
        kind=EventKind.INCIDENT,
        title="x",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
        poll_run=run,
    )
    assert Service.objects.filter(pk=service.pk).exists()

    body = staff_client.get(reverse(url_name)).content.decode()
    assert re.search(r'href="/admin/\w+/\w+/[0-9a-f-]{36}/change/"', body), (
        f"{url_name} has no row that leads anywhere"
    )


@pytest.mark.django_db
def test_a_service_shows_its_logo_and_falls_back_to_an_initial(staff_client):
    """A missing logo looks incomplete; a wrong one names the wrong thing.

    Unfold drops the initials when there is an image, which is the
    fallback the spec asks for.
    """
    from tests.factories import ServiceFactory

    ServiceFactory(name="Withlogo", logo="https://cdn.example/mark.png")
    ServiceFactory(name="Nologo", logo="")

    body = staff_client.get(
        reverse("admin:catalog_service_changelist")
    ).content.decode()
    assert "https://cdn.example/mark.png" in body
    assert "NO" in body  # the initial standing in for the missing one


@pytest.mark.django_db
def test_a_blank_interval_says_what_it_will_do(staff_client, settings):
    """Three empty boxes said nothing about inheriting a default.

    The number comes from settings at render time, so changing it does
    not want a migration to restate something the database never stores.
    """
    settings.POLL_INTERVAL_SECONDS = 900
    from tests.factories import ServiceFactory

    service = ServiceFactory()
    body = staff_client.get(
        reverse("admin:polling_poller_change", args=[service.poller.pk])
    ).content.decode()
    assert "deployment default of 900 seconds" in body
