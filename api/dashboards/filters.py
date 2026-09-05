from catalog.models import ServiceComponent
from common.filters import SeverityFilterMixin


class BoardComponentFilter(SeverityFilterMixin):
    class Meta:
        model = ServiceComponent
        fields = []
