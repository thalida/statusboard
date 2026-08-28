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
        url,
        {
            "slug": "from-popup",
            "name": "From popup",
            "description": "",
            "logo": "",
            "homepage_url": "",
            "watcher_count": 0,
            "_popup": "1",
            # The events inline. A browser posts this; the test must too.
            "events-TOTAL_FORMS": "0",
            "events-INITIAL_FORMS": "0",
            "events-MIN_NUM_FORMS": "0",
            "events-MAX_NUM_FORMS": "0",
            "status_page-TOTAL_FORMS": "0",
            "status_page-INITIAL_FORMS": "0",
            "status_page-MIN_NUM_FORMS": "0",
            "status_page-MAX_NUM_FORMS": "0",
        },
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
def test_poller_written_tables_are_not_editable(staff_client, label):
    # A hand-written row invents history the API serves, or trips the
    # one-open-status constraint, and the next poll overwrites it anyway.
    model = next(m for m in admin.site._registry if m._meta.label == label)
    site_admin = admin.site._registry[model]
    request = staff_client.request().wsgi_request
    assert not site_admin.has_add_permission(request)
    assert not site_admin.has_change_permission(request)
    assert not site_admin.has_delete_permission(request)


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
