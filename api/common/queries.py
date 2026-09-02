"""Query pieces that know nothing about one app.

`related_count` lived in `common.admin`, which made an admin module a
dependency of anything that counted a relation.
"""

from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce


def related_count(queryset, group_by, ref="pk"):
    """How many rows are on the other end, without joining to fetch them.

    Several counts on one row multiply into one another. Each is a
    join, so a service is read once per component per event. Each count
    asks its own question instead.
    """
    counted = (
        queryset.filter(**{group_by: OuterRef(ref)})
        .order_by()
        .values(group_by)
        .annotate(total=Count("pk"))
        .values("total")
    )
    return Coalesce(Subquery(counted, output_field=IntegerField()), 0)
