"""بارگذاری فاکتور و ثبت پرداخت توسط مدیر مالی."""

from __future__ import annotations

from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.constants.procurement import (
    REQUEST_TYPE_PURCHASE,
    STATUS_AWAITING_INVOICE,
    STATUS_COMPLETED,
)
from app.models.request import Request
from app.models.user import User
from app.services.attachment_service import (
    ENTITY_PROCUREMENT_INVOICE,
    list_attachments_serialized,
    save_entity_attachment,
)
from app.services.procurement.procurement_notifications import notify_finance_invoice_uploaded


def _require_purchase(db: Session, request_id: int) -> Request:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        raise ValueError("درخواست خرید یافت نشد")
    return req


def user_is_purchase_manager(user: User) -> bool:
    if not hasattr(user, "has_role"):
        return False
    return user.has_role("purchase_manager") or user.has_role("purchase_officer")


def user_is_finance_manager(user: User) -> bool:
    if not hasattr(user, "has_role"):
        return False
    return user.has_role("finance_manager") or user.has_role("accountant")


async def upload_purchase_invoice(
    db: Session,
    *,
    request_id: int,
    user: User,
    file: UploadFile,
) -> dict:
    req = _require_purchase(db, request_id)
    if req.status != STATUS_AWAITING_INVOICE:
        raise ValueError("در این مرحله امکان بارگذاری فاکتور نیست")
    if not user_is_purchase_manager(user):
        if not (hasattr(user, "has_permission") and user.has_permission("procurement.write")):
            raise ValueError("فقط مسئول خرید می‌تواند فاکتور بارگذاری کند")

    await save_entity_attachment(
        db,
        entity_type=ENTITY_PROCUREMENT_INVOICE,
        entity_id=request_id,
        uploaded_by_id=user.id,
        file=file,
    )
    db.commit()

    from app.constants.procurement import WORKFLOW_REF_PURCHASE
    from app.services.procurement.purchase_workflow import (
        ACTION_UPLOAD_INVOICE,
        complete_operational_step,
        get_active_purchase_workflow,
    )

    active = get_active_purchase_workflow(db, request_id)
    if active and active.ref_type == WORKFLOW_REF_PURCHASE:
        complete_operational_step(
            db,
            request_id=request_id,
            user_or_id=user,
            expected_action=ACTION_UPLOAD_INVOICE,
        )
    else:
        notify_finance_invoice_uploaded(db, request_id)
        db.commit()

    return {"items": list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id)}


def list_purchase_invoices(db: Session, request_id: int) -> list[dict]:
    _require_purchase(db, request_id)
    return list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id)


def mark_invoice_paid(db: Session, *, request_id: int, user: User) -> dict:
    req = _require_purchase(db, request_id)
    if req.status != STATUS_AWAITING_INVOICE:
        raise ValueError("فقط درخواست‌های در انتظار پرداخت فاکتور قابل تسویه هستند")
    if not user_is_finance_manager(user):
        if not (hasattr(user, "has_permission") and user.has_permission("workflow.approve")):
            raise ValueError("فقط مدیر مالی می‌تواند پرداخت فاکتور را ثبت کند")

    invoices = list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id)
    if not invoices:
        raise ValueError("ابتدا باید فاکتور توسط مسئول خرید بارگذاری شود")

    from app.constants.procurement import WORKFLOW_REF_PURCHASE
    from app.services.procurement.purchase_workflow import (
        ACTION_CONFIRM_PAYMENT,
        complete_operational_step,
        get_active_purchase_workflow,
    )

    active = get_active_purchase_workflow(db, request_id)
    if active and active.ref_type == WORKFLOW_REF_PURCHASE:
        complete_operational_step(
            db,
            request_id=request_id,
            user_or_id=user,
            expected_action=ACTION_CONFIRM_PAYMENT,
        )
    else:
        req.status = STATUS_COMPLETED
        req.invoice_paid_at = datetime.utcnow()
        req.invoice_paid_by = user.id
        db.commit()

    db.refresh(req)
    from app.services.procurement.purchase_request_service import serialize_purchase_request

    return serialize_purchase_request(db, req)
