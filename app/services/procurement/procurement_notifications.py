"""اعلان‌های اختصاصی گردش خرید کالا."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services.inbox import create_inbox_item
from app.services.notification import create_notification


def _users_with_role(db: Session, role_name: str) -> list[User]:
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return []
    rows = (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(UserRole.role_id == role.id, User.is_active == True)  # noqa: E712
        .all()
    )
    return rows


def _notify_users(
    db: Session,
    *,
    user_ids: list[int],
    title: str,
    message: str,
    notif_type: str,
    ref_id: int,
    ref_type: str = "request",
) -> None:
    seen: set[int] = set()
    for uid in user_ids:
        if uid in seen:
            continue
        seen.add(uid)
        create_notification(
            db,
            user_id=uid,
            title=title,
            message=message,
            type=notif_type,
            ref_id=ref_id,
            ref_type=ref_type,
        )
        create_inbox_item(
            db,
            role_id=None,
            title=title,
            message=message,
            ref_id=ref_id,
            ref_type=ref_type,
            preferred_user_id=uid,
        )
    db.commit()


def notify_purchase_team_proforma_needed(db: Session, request_id: int) -> None:
    users = _users_with_role(db, "purchase_manager")
    if not users:
        users = _users_with_role(db, "purchase_officer")
    _notify_users(
        db,
        user_ids=[u.id for u in users],
        title="ثبت پیش‌فاکتور",
        message=(
            f"درخواست خرید #{request_id} توسط مدیرعامل تأیید شد. "
            "لطفاً پیش‌فاکتور را بارگذاری و برای تأیید ارسال کنید."
        ),
        notif_type="procurement.proforma_needed",
        ref_id=request_id,
    )


def notify_after_proforma_ceo_approved(
    db: Session,
    *,
    request_id: int,
    payment_method: str | None,
    payment_comment: str | None,
) -> None:
    """اطلاع اختیاری به مالی درباره شرایط پرداخت — کارتابل مرحله بعد جداگانه از workflow می‌آید."""
    method_label = payment_method or "—"
    extra = f"\nتوضیح مدیرعامل: {payment_comment}" if payment_comment else ""
    finance_msg = (
        f"درخواست خرید #{request_id} تأیید شد. پرداخت با روش «{method_label}» انجام خواهد شد.{extra}\n"
        "پس از بارگذاری فاکتور توسط مسئول خرید، فاکتور را بررسی و پرداخت را ثبت کنید."
    )

    finance_users = _users_with_role(db, "finance_manager")
    _notify_users(
        db,
        user_ids=[u.id for u in finance_users],
        title="آماده پرداخت — روش پرداخت مشخص شد",
        message=finance_msg,
        notif_type="procurement.payment_planned",
        ref_id=request_id,
    )


def notify_finance_invoice_uploaded(db: Session, request_id: int) -> None:
    finance_users = _users_with_role(db, "finance_manager")
    _notify_users(
        db,
        user_ids=[u.id for u in finance_users],
        title="فاکتور خرید بارگذاری شد",
        message=(
            f"مسئول خرید فاکتور درخواست #{request_id} را بارگذاری کرد. "
            "لطفاً فاکتور را بررسی و پرداخت را ثبت کنید."
        ),
        notif_type="procurement.invoice_uploaded",
        ref_id=request_id,
    )
