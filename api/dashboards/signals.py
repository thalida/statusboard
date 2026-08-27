from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from dashboards.models import Dashboard


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_dashboard(sender, instance, created, **kwargs):
    """Give every new user a default board."""
    if created:
        Dashboard.objects.create(owner=instance, is_default=True)
