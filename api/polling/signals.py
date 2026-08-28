from django.db.models.signals import post_save
from django.dispatch import receiver

from catalog.models import Service
from polling.models import Poller


@receiver(post_save, sender=Service)
def create_poller(sender, instance, created, **kwargs):
    """Every service is polled, so every service has a Poller.

    The Poller carries tuning only, and every field falls back to the
    deployment default, so there is nothing to ask for at creation time.
    Without this, a service added anywhere but the import endpoint was
    never polled and never appeared as due.

    A StatusPage cannot be created the same way. It needs a URL, and there
    is no sensible default for one.
    """
    if created:
        Poller.objects.get_or_create(service=instance)
