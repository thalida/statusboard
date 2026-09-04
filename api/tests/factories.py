import factory
from django.contrib.auth import get_user_model

from catalog.models import Service, ServiceComponent, StatusPage
from polling.models import Poller


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    email = factory.Sequence(lambda n: f"watcher{n}@example.test")


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service
        # `tracked` makes rows on another table, never on this one, so
        # there is nothing to save afterwards.
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Service {n}")

    @factory.post_generation
    def tracked(service, create, count, **kwargs):
        """Put the service on somebody's board.

        `tracked=1` is one watcher, `tracked=2` is two. There is no
        column to set. A watcher is a row, and the count is worked out
        when it is read.
        """
        if not create or not count:
            return
        for _ in range(int(count)):
            track(ComponentFactory(service=service))


class StatusPageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StatusPage

    service = factory.SubFactory(ServiceFactory)
    url = factory.Sequence(lambda n: f"https://status{n}.example.com/")
    provider = "statuspage"


class PollerFactory(factory.django.DjangoModelFactory):
    """Tunes the Poller the Service signal already made.

    Creating a second one would trip the one-per-service constraint.
    """

    class Meta:
        model = Poller

    service = factory.SubFactory(ServiceFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        poller, _ = model_class.objects.get_or_create(service=kwargs.pop("service"))
        for field, value in kwargs.items():
            setattr(poller, field, value)
        poller.save()
        return poller


class ComponentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceComponent

    service = factory.SubFactory(ServiceFactory)
    external_id = factory.Sequence(lambda n: f"ext-{n}")
    name = factory.Sequence(lambda n: f"Component {n}")


def poll_run(service, **kwargs):
    """The fetch that a test says wrote its rows.

    `apply_fetch` takes one, and refuses a run from another service's
    poller. The run has to belong to the service being reconciled.

    The status page supplies the url and the provider. A test about the
    reconciliation does not have to make one.
    """
    from polling.models import PollRun

    page = getattr(service, "status_page", None) or StatusPageFactory(service=service)
    return PollRun.open(service.poller, page.url, page.provider, **kwargs)


def track(component, user=None):
    """Track a component, the way somebody using the app would.

    The user comes from `UserFactory`, which owns the one counter behind
    these addresses. A second counter here reset per test and collided
    with the factory's, on a column the database holds unique.
    """
    from dashboards.models import Dashboard, DashboardItem

    if user is None:
        user = UserFactory()
    board = user.dashboards.first() or Dashboard.objects.create(owner=user)
    return DashboardItem.objects.create(dashboard=board, component=component)


def ancestry(component):
    """The ids above it, root first, worked out from `parent`.

    `ServiceComponent.ancestors` is the one walk up the tree, and a
    breadcrumb reads the same order.
    """
    return [row.pk for row in component.ancestors]


def descendants(component):
    """The ids under it, at any depth, the way `?ancestor=` asks."""
    from catalog.queries import descendant_ids

    return set(
        ServiceComponent.objects.filter(
            pk__in=descendant_ids(component.pk)
        ).values_list("pk", flat=True)
    )


def watchers(component):
    """How many people track it, counted the way the app counts."""
    from catalog.queries import COMPONENT_WATCHER_COUNT

    return (
        ServiceComponent.objects.annotate(n=COMPONENT_WATCHER_COUNT)
        .get(pk=component.pk)
        .n
    )
