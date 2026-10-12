"""Framework-agnostic domain errors raised by the service layer.

`config.exception_handler` converts these into ``{code, message, field_errors}``
HTTP responses. Keeping them independent of DRF means admin actions and
management commands can reuse the same business rules, and any app (missions,
accounts, ...) can raise them without depending on another app.
"""


class DomainError(Exception):
    status_code = 400
    default_code = "error"
    default_message = "请求无法处理。"

    def __init__(self, message: str | None = None, *, code: str | None = None, field_errors: dict | None = None):
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.field_errors = field_errors or {}
        super().__init__(self.message)


class ValidationFailure(DomainError):
    status_code = 400
    default_code = "validation_error"
    default_message = "输入无效。"


class PermissionDenied(DomainError):
    status_code = 403
    default_code = "permission_denied"
    default_message = "没有权限执行该操作。"


class NotFound(DomainError):
    status_code = 404
    default_code = "not_found"
    default_message = "资源不存在。"


class ConflictError(DomainError):
    status_code = 409
    default_code = "conflict"
    default_message = "操作与当前状态冲突。"
