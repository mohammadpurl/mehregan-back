"""Standard API error body for frontend: code + message (+ detail for compatibility)."""

from typing import Any

from fastapi.encoders import jsonable_encoder

STATUS_DEFAULT_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
}

STATUS_DEFAULT_MESSAGES: dict[int, str] = {
    400: "درخواست نامعتبر است",
    401: "احراز هویت نشده‌اید",
    403: "دسترسی مجاز نیست",
    404: "مورد یافت نشد",
    409: "تداخل داده",
    422: "خطا در اعتبارسنجی ورودی",
    500: "خطای داخلی سرور",
}


def json_safe_detail(detail: Any) -> Any:
    """Ensure error payloads are JSON-serializable (e.g. Pydantic ctx.error ValueError)."""
    return jsonable_encoder(detail, custom_encoder={Exception: lambda e: str(e)})


def _finalize_error_body(body: dict[str, Any], status_code: int) -> dict[str, Any]:
    """Add RFC7807-compatible title/status alongside code/message/detail."""
    message = str(
        body.get("message")
        or body.get("detail")
        or body.get("title")
        or STATUS_DEFAULT_MESSAGES.get(status_code, "خطا")
    )
    body.setdefault("code", STATUS_DEFAULT_CODES.get(status_code, "HTTP_ERROR"))
    body["message"] = message
    raw_detail = body.get("detail", message)
    if isinstance(raw_detail, BaseException):
        raw_detail = str(raw_detail)
    body["detail"] = raw_detail if raw_detail is not None else message
    body["title"] = str(body.get("title") or message)
    body["status"] = int(body.get("status") or status_code)
    return body


def build_error_response(status_code: int, detail: Any) -> dict[str, Any]:
    """
    Normalize FastAPI HTTPException.detail into:
    { code, message, detail, title, status, ...optional fields }
    """
    if isinstance(detail, dict):
        code = str(detail.get("code") or STATUS_DEFAULT_CODES.get(status_code, "HTTP_ERROR"))
        message = str(
            detail.get("message")
            or detail.get("detail")
            or detail.get("title")
            or STATUS_DEFAULT_MESSAGES.get(status_code, "خطا")
        )
        raw_detail = detail.get("detail", message)
        body: dict[str, Any] = {
            "code": code,
            "message": message,
            "detail": str(raw_detail) if isinstance(raw_detail, BaseException) else raw_detail,
        }
        for key, value in detail.items():
            if key not in body:
                body[key] = json_safe_detail(value)
        return _finalize_error_body(body, status_code)

    if isinstance(detail, list):
        message = STATUS_DEFAULT_MESSAGES[422]
        safe_errors = json_safe_detail(detail)
        return _finalize_error_body(
            {
                "code": "VALIDATION_ERROR",
                "message": message,
                "detail": message,
                "errors": safe_errors,
            },
            status_code,
        )

    if isinstance(detail, BaseException):
        detail = str(detail)
    message = str(detail) if detail else STATUS_DEFAULT_MESSAGES.get(status_code, "خطا")
    code = STATUS_DEFAULT_CODES.get(status_code, "HTTP_ERROR")
    return _finalize_error_body(
        {"code": code, "message": message, "detail": message},
        status_code,
    )


def api_error_detail(
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    """Use as HTTPException(detail=api_error_detail(...))."""
    body: dict[str, Any] = {"code": code, "message": message, "detail": message}
    body.update(extra)
    return body
