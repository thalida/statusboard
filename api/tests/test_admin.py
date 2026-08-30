import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

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
        "Behind schedule",
        "Poll success",
        "Stalest service",
    ):
        assert card in body, f"{card} missing from the dashboard"
    for panel in ("Polls, last 24 hours", "Services tracked, last 30 days"):
        assert panel in body, f"{panel} missing from the dashboard"
    # Neither the catalog of every model nor a log of admin edits says
    # anything about whether polling works.
    assert "app-list" not in body
    assert "Recent actions" not in body


@pytest.mark.django_db
def test_the_environment_is_named_on_every_page(staff_client):
    # Acting on production believing it is development is the mistake worth
    # making loud.
    assert "Development" in staff_client.get(reverse("admin:index")).content.decode()


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
    "label", ["catalog.Service", "catalog.ServiceComponent", "polling.Poller"]
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


@pytest.mark.django_db
def test_a_poller_cannot_be_added_by_hand(staff_client):
    """One per service, made with the service.

    The column is one-to-one and a signal fills it, so an add form could
    only ever offer a duplicate the database refuses.
    """
    from polling.models import Poller

    site_admin = admin.site._registry[Poller]
    assert not site_admin.has_add_permission(staff_client.request().wsgi_request)
    assert staff_client.get(reverse("admin:polling_poller_add")).status_code == 403


@pytest.mark.django_db
def test_a_service_cannot_hold_two_pollers():
    # The database is the thing that guarantees it, not the admin.
    from django.db import IntegrityError

    from polling.models import Poller
    from tests.factories import ServiceFactory

    service = ServiceFactory()
    with pytest.raises(IntegrityError):
        Poller.objects.create(service=service)


@pytest.mark.django_db
def test_only_the_pause_is_open_on_the_polling_schedule():
    # Everything else either doubles the polling or sends the worker
    # somewhere that does not exist, and neither fails loudly.
    from django_celery_beat.models import PeriodicTask

    schedule_admin = admin.site._registry[PeriodicTask]
    readonly = schedule_admin.get_readonly_fields(None)

    assert "enabled" not in readonly
    for name in ["task", "args", "kwargs", "interval", "queue"]:
        assert name in readonly
    # `regtask` is not readonly, it is gone: a readonly form-only field
    # cannot be rendered and took the change page down with it.
    fields = [f for _, o in schedule_admin.get_fieldsets(None) for f in o["fields"]]
    assert "regtask" not in fields


@pytest.mark.django_db
def test_a_polling_schedule_cannot_be_added_or_deleted_by_hand():
    from django_celery_beat.models import PeriodicTask

    schedule_admin = admin.site._registry[PeriodicTask]

    assert not schedule_admin.has_add_permission(None)
    assert not schedule_admin.has_delete_permission(None)


@pytest.mark.django_db
def test_a_poll_run_reaches_what_it_wrote(staff_client):
    """The links off a run are a filter, and a filter must be permitted.

    Django refuses a lookup no filter declares, so a link like this stops
    working the moment the filter is dropped. It fails as a 400 on a page
    nothing else tests.
    """
    from polling.models import PollRun
    from tests.factories import ServiceFactory

    service = ServiceFactory()
    run = PollRun.objects.create(
        poller=service.poller,
        url="https://status.example.com/",
        provider="statuspage",
        started_at=timezone.now(),
        finished_at=timezone.now(),
        ok=True,
    )

    for view in ["status_componentstatus", "status_serviceevent"]:
        url = reverse(f"admin:{view}_changelist")
        response = staff_client.get(url, {"poll_run__id__exact": str(run.pk)})
        assert response.status_code == 200, view


@pytest.mark.django_db
def test_a_reading_says_which_poll_wrote_it(staff_client):
    # It is not an editable column, so the record is the only place left
    # to say it. Without this you could read it on the table alone.
    from status.choices import Severity, StatusSource
    from status.models import ComponentStatus
    from tests.factories import ComponentFactory

    reading = ComponentStatus.objects.create(
        component=ComponentFactory(),
        severity=Severity.OPERATIONAL,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )
    url = reverse("admin:status_componentstatus_change", args=[reading.pk])

    assert "Written by" in staff_client.get(url).content.decode()


PROJECT_APPS = {"authentication", "catalog", "dashboards", "polling", "status"}

PROJECT_ADMINS = [
    model for model in admin.site._registry if model._meta.app_label in PROJECT_APPS
]


@pytest.mark.parametrize("model", PROJECT_ADMINS, ids=lambda m: m._meta.label)
def test_every_filter_names_a_real_path(model):
    """A filter naming a path that does not exist fails only when used.

    Django answers an unrecognised lookup with a redirect, so a broken
    one reads as an empty page rather than as an error. A typo in a path
    is invisible until somebody picks that filter and gets nothing.
    """
    for entry in admin.site._registry[model].list_filter or []:
        path = entry[0] if isinstance(entry, tuple) else entry
        if not isinstance(path, str):
            continue  # A filter class brings its own queryset.
        target = model
        for part in path.split("__"):
            field = target._meta.get_field(part)
            if field.is_relation:
                target = field.related_model


@pytest.mark.django_db
@pytest.mark.parametrize("model", PROJECT_ADMINS, ids=lambda m: m._meta.label)
def test_every_filter_choice_opens(staff_client, model):
    """Every option a filter offers is one somebody can click.

    The paths are checked above. This is the other half: the option the
    page renders has to be one the changelist will accept back.
    """
    from django.test import RequestFactory

    opts = model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
    request = RequestFactory().get(url)
    request.user = User.objects.get(email="admin@example.com")
    model_admin = admin.site._registry[model]
    changelist = model_admin.get_changelist_instance(request)

    for spec in changelist.get_filters(request)[0]:
        for choice in spec.choices(changelist):
            query = choice.get("query_string")
            if not query:
                continue
            assert staff_client.get(url + query).status_code == 200, (
                f"{opts.label}: {query}"
            )


@pytest.mark.parametrize("model", PROJECT_ADMINS, ids=lambda m: m._meta.label)
def test_every_search_field_names_a_real_path(model):
    """A search path that does not resolve raises only when searched.

    The changelist renders fine until somebody types, so a typo sits
    there until a person hits it.
    """
    for path in admin.site._registry[model].search_fields or []:
        target = model
        for part in path.lstrip("^=@").split("__"):
            field = target._meta.get_field(part)
            if field.is_relation:
                target = field.related_model


@pytest.mark.django_db
@pytest.mark.parametrize("model", PROJECT_ADMINS, ids=lambda m: m._meta.label)
def test_every_table_can_be_searched(staff_client, model):
    # Every row hangs off a service somewhere, so the service's name is
    # the one term that should reach every table.
    opts = model._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")

    assert staff_client.get(url, {"q": "nothing matches this"}).status_code == 200
    assert admin.site._registry[model].search_fields, opts.label


@pytest.mark.django_db
def test_the_system_account_is_in_every_database():
    """It is made as migrate finishes, next to the content types.

    Made on first use instead, it was absent from a database until
    something happened to write a row, and the admin showed an author
    nobody could look up.
    """
    from api.defaults import SYSTEM_EMAIL

    assert User.objects.filter(email=SYSTEM_EMAIL).exists()


@pytest.mark.django_db
def test_the_system_account_cannot_be_deleted(staff_client):
    from django.test import RequestFactory

    from api.defaults import SYSTEM_EMAIL

    admin_user = User.objects.get(email="admin@example.com")
    request = RequestFactory().get("/")
    request.user = admin_user
    user_admin = admin.site._registry[User]

    assert not user_admin.has_delete_permission(
        request, User.objects.get(email=SYSTEM_EMAIL)
    )
    assert user_admin.has_delete_permission(request, admin_user)


@pytest.mark.django_db
def test_the_admin_cannot_overwrite_a_password_with_plain_text(staff_client):
    """The field shows the hash. It must not take one.

    A plain field writes whatever is typed straight into the column, so
    a new password there is stored as the hash: the account can never
    sign in again, and the password is readable in the database.
    """
    from django.contrib import admin as django_admin

    user = User.objects.get(email="admin@example.com")
    stored = user.password
    user_admin = django_admin.site._registry[User]

    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = user
    form_class = user_admin.get_form(request, user, change=True)
    form = form_class(
        instance=user,
        data={"email": user.email, "password": "hunter2", "is_active": "on"},
    )

    assert form.is_valid(), dict(form.errors)
    form.save()
    user.refresh_from_db()
    assert user.password == stored
    assert user.check_password("admin-only")


@pytest.mark.django_db
def test_the_default_board_is_searched_not_listed(staff_client):
    """A dropdown would carry every board of every owner.

    The widget is the admin's autocomplete, which is served by the board
    admin's own search.
    """
    from django.test import RequestFactory

    from dashboards.models import Dashboard

    user = User.objects.get(email="admin@example.com")
    assert "default_dashboard" in admin.site._registry[User].autocomplete_fields

    request = RequestFactory().get("/")
    request.user = user
    board_admin = admin.site._registry[Dashboard]
    found, _ = board_admin.get_search_results(
        request, board_admin.get_queryset(request), user.default_dashboard.name
    )
    assert found.exists()


@pytest.mark.django_db
def test_a_person_cannot_open_somebody_elses_board():
    # The column cannot say whose board it names, so nothing else stops
    # it naming another owner's.
    from django.core.exceptions import ValidationError as Invalid

    mine = User.objects.create(email="a@b.com")
    theirs = User.objects.create(email="c@d.com")

    mine.default_dashboard = theirs.default_dashboard
    with pytest.raises(Invalid):
        mine.full_clean()


@pytest.mark.django_db
def test_the_polling_schedule_page_opens(staff_client):
    """Readonly is not free: Django drops a readonly field from the form.

    `regtask` is a form-only picker, so making it readonly left nothing
    to resolve it against and the change page raised. Nothing else here
    opens that page.
    """
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every = IntervalSchedule.objects.create(every=5, period=IntervalSchedule.MINUTES)
    task = PeriodicTask.objects.create(
        name="poll", task="polling.tasks.enqueue_due_polls", interval=every
    )
    url = reverse("admin:django_celery_beat_periodictask_change", args=[task.pk])

    assert staff_client.get(url).status_code == 200
