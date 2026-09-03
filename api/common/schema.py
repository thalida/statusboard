from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter

from common.filters import FIELDS_DESCRIPTION

FIELDS_PARAMETER = OpenApiParameter(
    name="fields",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description=FIELDS_DESCRIPTION,
)


class FieldsAutoSchema(AutoSchema):
    """Declare `?fields=` on every GET, list or detail.

    drf-spectacular only asks filter backends for parameters on list
    operations. Sparse fieldsets are a base-layer concern. They prune a
    detail response too. So the parameter is declared here. It is not
    annotated onto each detail view.
    """

    def get_override_parameters(self):
        parameters = list(super().get_override_parameters())
        if self.method.lower() == "get":
            parameters.append(FIELDS_PARAMETER)
        return parameters
