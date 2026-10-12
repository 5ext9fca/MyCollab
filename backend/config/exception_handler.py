"""Consistent API error shape: ``{code, message, field_errors}``.

Domain errors raised by the service layer are translated here, and built-in DRF
errors are normalized to the same envelope so the frontend has one format to
handle.
"""

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions import DomainError

_STATUS_CODE_NAMES = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    415: "unsupported_media_type",
    429: "throttled",
}


def _normalize_drf_response(response):
    if response.status_code == 400 and isinstance(response.data, dict):
        return Response(
            {
                "code": "validation_error",
                "message": "输入校验失败。",
                "field_errors": response.data,
            },
            status=response.status_code,
        )
    code = _STATUS_CODE_NAMES.get(response.status_code, "error")
    detail = response.data.get("detail") if isinstance(response.data, dict) else response.data
    return Response(
        {"code": code, "message": str(detail) if detail else code, "field_errors": {}},
        status=response.status_code,
    )


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response(
            {
                "code": exc.code,
                "message": exc.message,
                "field_errors": exc.field_errors,
            },
            status=exc.status_code,
        )
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    return _normalize_drf_response(response)
