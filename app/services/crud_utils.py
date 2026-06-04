def is_editable_status(status: str | None) -> bool:
    return (status or "").upper() in {"PENDING", "DRAFT"}


def ensure_editable(entity, *, status_attr: str = "status") -> None:
    status = getattr(entity, status_attr, None)
    if not is_editable_status(status):
        raise ValueError(
            "فقط رکوردهای در وضعیت پیش‌نویس یا در انتظار قابل ویرایش یا حذف هستند"
        )
