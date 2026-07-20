"""پیشنهاد و نرمال‌سازی عنوان درخواست‌ها."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.workflow_messages import REF_TYPE_LABELS, ref_type_label


def user_display_name(user: User | None) -> str:
    if not user:
        return "کاربر"
    parts = [
        (user.first_name or "").strip(),
        (user.last_name or "").strip(),
    ]
    name = " ".join(p for p in parts if p).strip()
    if name:
        return name
    return (user.full_name or user.username or "کاربر").strip() or "کاربر"


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل میلادی به شمسی (بدون وابستگی خارجی)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def format_jalali_date(day: date) -> str:
    """مثلاً 1404/04/29"""
    jy, jm, jd = _gregorian_to_jalali(day.year, day.month, day.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def suggest_request_title(
    *,
    type_label: str,
    requester_name: str,
    when: date | datetime | None = None,
) -> str:
    """پیشنهاد عنوان: نوع — تاریخ شمسی — نام درخواست‌دهنده."""
    if isinstance(when, datetime):
        day = when.date()
    elif isinstance(when, date):
        day = when
    else:
        day = date.today()
    label = (type_label or "درخواست").strip() or "درخواست"
    name = (requester_name or "کاربر").strip() or "کاربر"
    return f"{label} — {format_jalali_date(day)} — {name}"[:255]


def resolve_request_title(
    *,
    title: str | None,
    type_label: str,
    requester_name: str,
    when: date | datetime | None = None,
) -> str:
    """اگر کاربر عنوان داده همان؛ وگرنه پیشنهاد خودکار."""
    cleaned = (title or "").strip()
    if cleaned:
        return cleaned[:255]
    return suggest_request_title(
        type_label=type_label, requester_name=requester_name, when=when
    )


def suggest_title_for_ref_type(
    db: Session,
    *,
    ref_type: str,
    user: User,
    when: date | datetime | None = None,
) -> str:
    from app.services.workflow_feed_context import PAYMENT_TYPE_LABELS

    rt = (ref_type or "").strip()
    if rt in PAYMENT_TYPE_LABELS:
        label = PAYMENT_TYPE_LABELS[rt]
    elif rt in REF_TYPE_LABELS:
        label = REF_TYPE_LABELS[rt]
    else:
        label = ref_type_label(rt)
    return suggest_request_title(
        type_label=label,
        requester_name=user_display_name(user),
        when=when,
    )


def type_label_for_payment_type(payment_type: str | None) -> str:
    from app.services.workflow_feed_context import PAYMENT_TYPE_LABELS

    pt = (payment_type or "").strip().lower()
    if pt in PAYMENT_TYPE_LABELS:
        return PAYMENT_TYPE_LABELS[pt]
    if pt == "payment_order":
        return "دستور پرداخت"
    return REF_TYPE_LABELS.get("payment_request", "درخواست مالی")
