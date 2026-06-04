"""اتصال درخواست خرید به ماژول پرداخت (فاز ۵)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.constants.payment_types import PAYMENT_TYPE_PROCUREMENT
from app.constants.procurement import (
    REQUEST_TYPE_PURCHASE,
    STATUS_PAYMENT_PENDING,
    STATUS_READY_FOR_PAYMENT,
    STATUS_RECEIVING,
)
from app.models.payment_request import PaymentRequest
from app.models.procurement.proforma import ProcurementProforma
from app.models.request import Request
from app.models.workflow_instance import WorkflowInstance
from app.services.payment_request import create_payment_order, create_payment_request
from app.services.procurement.goods_receipt_service import _approved_proforma


def _workflow_instance_id_for_payment(db: Session, payment_request_id: int) -> int | None:
    inst = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == "payment_request",
            WorkflowInstance.ref_id == payment_request_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )
    return inst.id if inst else None


def get_procurement_payment_summary(db: Session, purchase_request: Request) -> dict | None:
    if not purchase_request.payment_request_id:
        return None
    pr = db.get(PaymentRequest, purchase_request.payment_request_id)
    if not pr:
        return None
    return {
        "id": pr.id,
        "amount": float(pr.amount),
        "status": pr.status,
        "payment_type": pr.payment_type,
        "workflow_instance_id": _workflow_instance_id_for_payment(db, pr.id),
    }


def create_procurement_payment(
    db: Session,
    *,
    request_id: int,
    user_id: int,
    counterparty_id: int | None = None,
    counterparty_bank_account_id: int | None = None,
    payer_company_account_id: int | None = None,
    payment_method: str | None = None,
    payment_date: date | None = None,
    notes: str | None = None,
    assignees_by_order: dict[str, int] | None = None,
) -> dict:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        raise ValueError("درخواست خرید یافت نشد")
    if req.status != STATUS_READY_FOR_PAYMENT:
        raise ValueError("فقط درخواست‌های «آماده پرداخت» قابل ثبت درخواست پرداخت هستند")
    if req.payment_request_id:
        raise ValueError("برای این درخواست قبلاً درخواست پرداخت ثبت شده است")

    proforma = _approved_proforma(db, request_id)
    if not proforma:
        raise ValueError("پیش‌فاکتور تأییدشده یافت نشد")

    from app.models.procurement.supplier import Supplier

    supplier = db.get(Supplier, proforma.supplier_id)
    supplier_label = supplier.name if supplier else f"تأمین‌کننده #{proforma.supplier_id}"
    reason = (notes or "").strip() or f"پرداخت خرید — درخواست #{request_id} — {supplier_label}"
    amount = float(proforma.amount)

    if counterparty_id and counterparty_bank_account_id and payment_method:
        payment_data = create_payment_order(
            db,
            user_id,
            payment_order_kind="individual",
            counterparty_id=counterparty_id,
            amount=amount,
            payment_method=payment_method,
            payer_company_account_id=payer_company_account_id,
            counterparty_bank_account_id=counterparty_bank_account_id,
            payment_date=payment_date,
            reason=reason,
            assignees_by_order=assignees_by_order,
        )
        payment_id = int(payment_data["id"])
    else:
        payment_data = create_payment_request(
            db=db,
            requester_id=user_id,
            payment_type=PAYMENT_TYPE_PROCUREMENT,
            amount=amount,
            payer_account="تعیین توسط مالی",
            receiver_account=supplier_label,
            payment_date=payment_date,
            reason=reason,
            assignees_by_order=assignees_by_order,
        )
        payment_id = int(payment_data["id"])

    req.payment_request_id = payment_id
    req.status = STATUS_PAYMENT_PENDING
    db.commit()
    db.refresh(req)

    return {
        "purchase_request_id": request_id,
        "purchase_request_status": req.status,
        "payment_request": payment_data,
    }


def on_procurement_payment_workflow_approved(db: Session, payment_request_id: int) -> None:
    """پس از تأیید گردش‌کار پرداخت، درخواست خرید به مرحله دریافت انبار می‌رود."""
    purchase_req = (
        db.query(Request)
        .filter(
            Request.type == REQUEST_TYPE_PURCHASE,
            Request.payment_request_id == payment_request_id,
        )
        .first()
    )
    if not purchase_req:
        return

    pr = db.get(PaymentRequest, payment_request_id)
    if pr and pr.payment_type == PAYMENT_TYPE_PROCUREMENT:
        pr.status = "APPROVED"

    if purchase_req.status in (STATUS_READY_FOR_PAYMENT, STATUS_PAYMENT_PENDING):
        purchase_req.status = STATUS_RECEIVING
    db.commit()
