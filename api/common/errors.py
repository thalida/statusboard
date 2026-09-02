"""One shape for every failure, and the codes that name them.

`ErrorSerializer` and the codes were declared and documented from the
start, and nothing raised them. Three different shapes came back
instead: DRF's `detail`, a field map from a serializer, and an
uncaught exception as a 500.

A client is generated from the contract, so it looks for `code` and
found it on nothing.
"""

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, Throttled
from rest_framework.views import exception_handler as drf_handler

from common.serializers import ERROR_CODES


class CodedError(APIException):
    """A failure that names itself.

    The code is what a client branches on. The detail is for a person.
    """

    def __init__(self, code, detail, status_code=status.HTTP_400_BAD_REQUEST):
        assert code in ERROR_CODES, f"{code!r} is not a code the contract names."
        self.code = code
        self.status_code = status_code
        super().__init__(detail)


class ProviderUnreachable(CodedError):
    def __init__(self, detail):
        super().__init__("provider_unreachable", detail, status.HTTP_502_BAD_GATEWAY)


class NoStatusPageFound(CodedError):
    def __init__(self, detail):
        super().__init__("no_status_page_found", detail)


def _code(exception):
    """The contract's name for this failure."""
    if isinstance(exception, CodedError):
        return exception.code
    if isinstance(exception, Throttled):
        return "throttled"
    # Django raises its own 404 and DRF translates it, so the exception
    # reaching here is `Http404` rather than DRF's `NotFound`.
    if isinstance(exception, NotFound | Http404):
        return "not_found"
    return None


def handler(exception, context):
    """Shape what DRF already handled, and leave the rest alone.

    A validation error keeps its field map: the client needs to know
    which field, and one `detail` string cannot say.
    """
    response = drf_handler(exception, context)
    if response is None:
        return None
    code = _code(exception)
    if code is None:
        return response
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    response.data = {"code": code, "detail": str(detail or exception)}
    return response
