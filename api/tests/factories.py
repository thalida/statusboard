import factory

from catalog.models import Service, ServiceComponent, StatusPage
from polling.models import Poller


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    slug = factory.Sequence(lambda n: f"service-{n}")
    name = factory.Sequence(lambda n: f"Service {n}")


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
