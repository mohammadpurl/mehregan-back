"""متن‌های فارسی برای inbox و اعلان‌های گردش‌کار."""

from __future__ import annotations

REF_TYPE_LABELS: dict[str, str] = {
    "payment_request": "درخواست مالی",
    "payment_order": "دستور پرداخت",
    "financial_document": "سند مالی",
    "petty_cash": "تنخواه",
    "petty_cash_settlement": "تسویه تنخواه",
    "mission_request": "درخواست ماموریت",
    "mission_report": "گزارش ماموریت",
    "workflow_form": "درخواست اداری",
    "warehouse_form": "فرم انبار",
    "procurement": "درخواست خرید",
    "product_request": "درخواست کالا",
    "purchase_request": "درخواست خرید کالا",
    "request": "درخواست خرید",
    "procurement_proforma": "پیش‌فاکتور خرید",
}

DEFAULT_REF_LABEL = "گردش‌کار"


def ref_type_label(ref_type: str | None) -> str:
    if not ref_type:
        return DEFAULT_REF_LABEL
    return REF_TYPE_LABELS.get(str(ref_type).strip(), str(ref_type))


def _label_from_ctx(ctx: object | None, ref_type: str | None = None) -> str:
    if ctx is not None:
        detail = getattr(ctx, "display_label", None)
        if detail:
            return str(detail)
    return ref_type_label(ref_type)


def _ref_suffix(ctx: object | None) -> str:
    ref_id = getattr(ctx, "business_ref_id", None) if ctx is not None else None
    if ref_id:
        return f" #{ref_id}"
    return ""


def _requester_suffix(ctx: object | None) -> str:
    name = getattr(ctx, "requester_name", None) if ctx is not None else None
    if name:
        return f" — {name}"
    return ""


def inbox_title_for_step(
    ref_type: str | None = None,
    step_order: int | None = None,
    ctx: object | None = None,
) -> str:
    label = _label_from_ctx(ctx, ref_type)
    suffix = _ref_suffix(ctx)
    if step_order is not None and step_order > 0:
        return f"تأیید {label}{suffix} — مرحله {step_order}"
    return f"تأیید {label}{suffix}"


def inbox_message_for_step(
    ref_type: str | None = None,
    step_order: int | None = None,
    ctx: object | None = None,
) -> str:
    label = _label_from_ctx(ctx, ref_type)
    suffix = _ref_suffix(ctx)
    requester = _requester_suffix(ctx)
    if step_order is not None and step_order > 0:
        return (
            f"یک {label}{suffix} در مرحله {step_order} منتظر بررسی و تأیید شماست.{requester}"
        )
    return f"یک {label}{suffix} منتظر بررسی و تأیید شماست.{requester}"


def notification_title_for_step(
    ref_type: str | None = None,
    ctx: object | None = None,
) -> str:
    label = _label_from_ctx(ctx, ref_type)
    suffix = _ref_suffix(ctx)
    return f"کار جدید: {label}{suffix}"


def notification_message_for_step(
    ref_type: str | None = None,
    step_order: int | None = None,
    ctx: WorkflowNotifyContext | None = None,
) -> str:
    return inbox_message_for_step(ref_type, step_order, ctx)


def notification_title_rejected(label: str) -> str:
    return f"رد شد: {label}"


def notification_message_rejected(label: str, *, comment: str | None = None) -> str:
    msg = f"{label} شما رد شد."
    if comment and comment.strip():
        msg += f" دلیل: {comment.strip()}"
    return msg


def notification_title_step_approved(label: str, *, step_order: int | None = None) -> str:
    if step_order is not None and step_order > 0:
        return f"تأیید مرحله {step_order}: {label}"
    return f"تأیید شد: {label}"


def notification_message_step_approved(
    label: str,
    *,
    step_order: int | None = None,
    actor_name: str | None = None,
    final: bool = False,
) -> str:
    who = f" توسط {actor_name}" if actor_name else ""
    if final:
        return f"{label} شما{who} به‌طور کامل تأیید شد."
    if step_order is not None and step_order > 0:
        return f"مرحله {step_order} از {label} شما{who} تأیید شد."
    return f"{label} شما{who} تأیید شد."


def notification_title_step_rejected(
    label: str,
    *,
    step_order: int | None = None,
    returned_to_previous: bool = False,
) -> str:
    if returned_to_previous:
        return f"بازگشت برای اصلاح: {label}"
    if step_order is not None and step_order > 0:
        return f"رد مرحله {step_order}: {label}"
    return f"رد شد: {label}"


def notification_message_step_rejected(
    label: str,
    *,
    step_order: int | None = None,
    actor_name: str | None = None,
    comment: str | None = None,
    returned_to_previous: bool = False,
) -> str:
    who = f" توسط {actor_name}" if actor_name else ""
    if returned_to_previous:
        msg = (
            f"مرحله {step_order} از {label} شما{who} رد شد و برای اصلاح به مرحله قبل برگشت."
            if step_order is not None and step_order > 0
            else f"{label} شما{who} رد شد و برای اصلاح به مرحله قبل برگشت."
        )
    elif step_order is not None and step_order > 0:
        msg = f"مرحله {step_order} از {label} شما{who} رد شد."
    else:
        msg = f"{label} شما{who} رد شد."
    if comment and comment.strip():
        msg += f" دلیل: {comment.strip()}"
    return msg
