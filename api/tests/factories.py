import factory

from catalog.models import Poller, Service, ServiceComponent, StatusPage


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
    class Meta:
        model = Poller

    service = factory.SubFactory(ServiceFactory)


class ComponentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ServiceComponent

    service = factory.SubFactory(ServiceFactory)
    external_id = factory.Sequence(lambda n: f"ext-{n}")
    name = factory.Sequence(lambda n: f"Component {n}")
