from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from dashboards.models import DashboardItem


@receiver([post_save, post_delete], sender=DashboardItem)
def refresh_watcher_count(sender, instance, **kwargs):
    """Recount the service this row tracks, however the row changed.

    Overriding `save` and `delete` on the model missed four paths.
    Closing an account, deleting a board and `queryset.delete()` all
    cascade in SQL, and none of them calls the method. A service kept a
    watcher who no longer existed, so the poller kept polling it.

    Django sends these signals for a cascade, so this catches all three.
    It cannot catch `bulk_create`, which sends nothing. Nothing in this
    project uses it on this table.
    """
    instance.component.service.refresh_watcher_count()
