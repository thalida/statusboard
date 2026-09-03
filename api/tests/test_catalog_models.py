import pytest
from django.db.utils import IntegrityError

from catalog.models import Service, ServiceComponent, StatusPage
from polling.reconcile import rebuild_ancestry
from tests.factories import (
    ComponentFactory,
    PollerFactory,
    ServiceFactory,
    UserFactory,
    track,
    watchers,
)


def test_a_components_watcher_count_is_distinct_users(db):
    # Two boards holding one component is two watchers. One person
    # holding it twice is impossible, and one holding a sibling too is
    # still one watcher of this component.
    component = ComponentFactory()
    sibling = ComponentFactory(service=component.service)
    first = UserFactory()
    track(component, user=first)
    track(sibling, user=first)
    track(component, user=UserFactory())

    assert watchers(component) == 2
    assert watchers(sibling) == 1


@pytest.mark.django_db
def test_a_component_is_identified_by_external_id_not_by_name():
    # Names change. Provider ids do not.
    # A name match orphans a tracked row on the first rename.
    service = ServiceFactory()
    ComponentFactory(service=service, external_id="abc", name="SMS")
    with pytest.raises(IntegrityError):
        ComponentFactory(
            service=service, external_id="abc", name="Programmable Messaging"
        )


@pytest.mark.django_db
def test_the_same_external_id_may_exist_under_a_different_service():
    ComponentFactory(service=ServiceFactory(slug="a"), external_id="abc")
    ComponentFactory(service=ServiceFactory(slug="b"), external_id="abc")
    assert ServiceComponent.objects.filter(external_id="abc").count() == 2


@pytest.mark.django_db
def test_status_page_url_is_the_dedupe_key():
    StatusPage.objects.create(
        service=ServiceFactory(slug="a"), url="https://x/", provider="statuspage"
    )
    with pytest.raises(IntegrityError):
        StatusPage.objects.create(
            service=ServiceFactory(slug="b"), url="https://x/", provider="statuspage"
        )


@pytest.mark.django_db
def test_poller_intervals_are_null_to_inherit_the_deployment_default():
    # The Service signal makes it, so there is one to read already.
    poller = ServiceFactory().poller
    assert poller.interval_seconds is None
    assert poller.effective_interval_seconds == 300


@pytest.mark.django_db
def test_a_service_can_override_the_interval():
    poller = PollerFactory(service=ServiceFactory(), interval_seconds=60)
    assert poller.effective_interval_seconds == 60


@pytest.mark.django_db
def test_a_component_can_be_archived_rather_than_deleted():
    # Someone may track this component.
    # Deletion removes it from their board with no warning.
    component = ComponentFactory()
    assert Service.objects.count() == 1
    component.is_archived = True
    component.save()
    component.refresh_from_db()
    assert component.is_archived
    assert component.archived_at is not None


@pytest.mark.django_db
def test_a_service_slugs_itself_from_its_name():
    # Nobody should have to type the URL of a service they are adding.
    assert Service.objects.create(name="Twilio SendGrid").slug == "twilio-sendgrid"


@pytest.mark.django_db
def test_a_second_service_with_the_same_name_gets_a_counter():
    # Two providers really can share a name, so this cannot just fail.
    Service.objects.create(name="Status")
    assert Service.objects.create(name="Status").slug == "status-2"
    assert Service.objects.create(name="Status").slug == "status-3"


@pytest.mark.django_db
def test_a_slug_given_by_hand_is_kept():
    assert Service.objects.create(name="Twilio", slug="twil").slug == "twil"


@pytest.mark.django_db
def test_renaming_a_service_does_not_move_its_slug():
    # The slug is the service's public URL. A rename must not break it.
    service = Service.objects.create(name="Twilio")
    service.name = "Twilio Messaging"
    service.save()
    assert service.slug == "twilio"


@pytest.mark.django_db
def test_a_name_with_no_slug_characters_still_gets_one():
    assert Service.objects.create(name="!!!").slug == "service"


@pytest.mark.django_db
def test_archiving_sets_the_date():
    # `updated_at` cannot answer when a provider dropped a component: it
    # moves on every save, so a later rename would erase it.
    component = ComponentFactory()
    assert component.archived_at is None

    component.is_archived = True
    component.save()

    assert component.archived_at is not None


@pytest.mark.django_db
def test_unarchiving_clears_the_date():
    component = ComponentFactory()
    component.is_archived = True
    component.save()

    component.is_archived = False
    component.save()

    assert component.archived_at is None


@pytest.mark.django_db
def test_the_flag_and_the_date_cannot_disagree():
    """One fact, two columns, so the database holds them together.

    A bulk update never reaches `save`, which is the path that would
    otherwise let them come apart quietly.
    """
    from django.db import IntegrityError, transaction

    from catalog.models import ServiceComponent

    component = ComponentFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ServiceComponent.objects.filter(pk=component.pk).update(is_archived=True)


def test_ancestor_ids_are_stored_top_down(db):
    # A descendant query reads this array. Walking `parent` per row
    # cannot use an index, and `for_display` only selects two levels up.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)
    rebuild_ancestry(service)

    leaf.refresh_from_db()
    assert leaf.ancestor_ids == [top.id, middle.id]

    # Every descendant, not the direct children. `top` has two below it.
    assert ServiceComponent.objects.filter(ancestor_ids__contains=[top.id]).count() == 2


def test_for_display_counts_descendants_without_a_query_a_row(
    db, django_assert_num_queries
):
    # The count is why `for_display` exists. Asked per row, a page of
    # fifty components costs fifty extra queries.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    ComponentFactory(service=service, parent=middle)
    rebuild_ancestry(service)

    rows = list(ServiceComponent.objects.for_display())
    with django_assert_num_queries(0):
        counts = sorted(row.descendant_count() for row in rows)

    # Two below the top, one below the middle, none below the leaf.
    assert counts == [0, 1, 2]
