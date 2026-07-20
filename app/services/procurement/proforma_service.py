"""پیش‌فاکتور درخواست خرید — آپلود، بایگانی، workflow مرحله ۲."""

from __future__ import annotations

from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.constants.procurement import (
    PROFORMA_STATUS_APPROVED,
    PROFORMA_STATUS_DRAFT,
    PROFORMA_STATUS_SUBMITTED,
    REQUEST_TYPE_PURCHASE,
    STATUS_AWAITING_PROFORMA,
    STATUS_PROFORMA_REVIEW,
    STATUS_AWAITING_INVOICE,
    WORKFLOW_REF_PROFORMA,
)
from app.infrastructure.messaging.publisher import publish_event
from app.models.procurement.proforma import ProcurementProforma
from app.models.procurement.supplier import Supplier
from app.models.request import Request
from app.services.attachment_service import (
    ENTITY_PROCUREMENT_PROFORMA,
    list_attachments,
    save_entity_attachment,
    serialize_attachment,
)
from app.services.workflow_start import start_workflow_instance


def _require_purchase_request(db: Session, request_id: int) -> Request:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        raise ValueError("درخواست خرید یافت نشد")
    return req


def serialize_proforma(db: Session, row: ProcurementProforma) -> dict:
    supplier = db.get(Supplier, row.supplier_id) if row.supplier_id else None
    atts = list_attachments(db, ENTITY_PROCUREMENT_PROFORMA, row.id)
    att = serialize_attachment(atts[0]) if atts else {}
    amount = float(row.amount)
    download = att.get("download_url") or att.get("url")
    preview = att.get("preview_url") or (
        f"{download}?inline=1" if download and "inline=" not in str(download) else download
    )
    return {
        "id": row.id,
        "request_id": row.request_id,
        "supplier_id": row.supplier_id,
        "supplier_name": supplier.name if supplier else None,
        "amount": amount,
        "total_amount": amount,
        "notes": row.notes,
        "status": row.status,
        "uploaded_by": row.uploaded_by,
        "created_at": row.created_at,
        "attachment_id": att.get("id"),
        "file_name": att.get("file_name"),
        "content_type": att.get("content_type"),
        "download_url": download,
        "preview_url": preview,
        "preview_file_url": att.get("preview_file_url") or att.get("file_url"),
        "file_url": att.get("file_url"),
    }


async def create_proforma(
    db: Session,
    *,
    request_id: int,
    user_id: int,
    amount: float,
    file: UploadFile,
    supplier_id: int | None = None,
    notes: str | None = None,
) -> dict:
    from app.services.procurement.purchase_request_service import (
        sync_purchase_request_status_from_workflow,
    )

    sync_purchase_request_status_from_workflow(db, request_id)
    req = _require_purchase_request(db, request_id)
    if req.status not in (STATUS_AWAITING_PROFORMA, STATUS_PROFORMA_REVIEW):
        raise ValueError(
            "در این مرحله امکان ثبت پیش‌فاکتور نیست. "
            "ابتدا مراحل قبلی باید تکمیل شده باشد."
        )

    resolved_supplier_id = int(supplier_id) if supplier_id else None
    if resolved_supplier_id:
        supplier = db.get(Supplier, resolved_supplier_id)
        if not supplier or not supplier.is_active:
            raise ValueError("تأمین‌کننده یافت نشد یا غیرفعال است")

    if amount <= 0:
        raise ValueError("مبلغ پیش‌فاکتور باید بیشتر از صفر باشد")

    row = ProcurementProforma(
        request_id=request_id,
        supplier_id=resolved_supplier_id,
        amount=amount,
        notes=(notes or "").strip() or None,
        status=PROFORMA_STATUS_DRAFT,
        uploaded_by=user_id,
    )
    db.add(row)
    db.flush()

    await save_entity_attachment(
        db,
        entity_type=ENTITY_PROCUREMENT_PROFORMA,
        entity_id=row.id,
        uploaded_by_id=user_id,
        file=file,
    )
    db.commit()
    db.refresh(row)
    return serialize_proforma(db, row)


async def update_draft_proforma(
    db: Session,
    *,
    request_id: int,
    proforma_id: int,
    user_id: int,
    supplier_id: int | None = None,
    amount: float | None = None,
    file: UploadFile | None = None,
    notes: str | None = None,
) -> dict:
    """ویرایش پیش‌فاکتور پیش‌نویس: مبلغ کل، تأمین‌کننده، فایل."""
    req = _require_purchase_request(db, request_id)
    if req.status not in (STATUS_AWAITING_PROFORMA, STATUS_PROFORMA_REVIEW):
        raise ValueError("در این مرحله امکان ویرایش پیش‌فاکتور نیست")

    row = db.get(ProcurementProforma, proforma_id)
    if not row or row.request_id != request_id:
        raise ValueError("پیش‌فاکتور یافت نشد")
    if row.status != PROFORMA_STATUS_DRAFT:
        raise ValueError("فقط پیش‌فاکتور پیش‌نویس قابل ویرایش است")

    if supplier_id is not None:
        if supplier_id:
            supplier = db.get(Supplier, supplier_id)
            if not supplier or not supplier.is_active:
                raise ValueError("تأمین‌کننده یافت نشد یا غیرفعال است")
            row.supplier_id = supplier_id
        else:
            row.supplier_id = None

    if amount is not None:
        if amount <= 0:
            raise ValueError("مبلغ پیش‌فاکتور باید بیشتر از صفر باشد")
        row.amount = amount

    if notes is not None:
        row.notes = notes.strip() or None

    if file is not None and getattr(file, "filename", None):
        await save_entity_attachment(
            db,
            entity_type=ENTITY_PROCUREMENT_PROFORMA,
            entity_id=row.id,
            uploaded_by_id=user_id,
            file=file,
        )

    db.commit()
    db.refresh(row)
    return serialize_proforma(db, row)


def list_proformas_for_request(db: Session, request_id: int) -> list[dict]:
    rows = (
        db.query(ProcurementProforma)
        .filter(ProcurementProforma.request_id == request_id)
        .order_by(ProcurementProforma.id.desc())
        .all()
    )
    return [serialize_proforma(db, r) for r in rows]


def list_proformas_for_supplier(
    db: Session, supplier_id: int, *, include_archived: bool = True
) -> list[dict]:
    query = db.query(ProcurementProforma).filter(
        ProcurementProforma.supplier_id == supplier_id
    )
    if not include_archived:
        query = query.filter(ProcurementProforma.archived_at.is_(None))
    rows = query.order_by(ProcurementProforma.id.desc()).all()
    return [serialize_proforma(db, r) for r in rows]


def submit_proforma_for_approval(
    db: Session, *, request_id: int, proforma_id: int, user_id: int
) -> dict:
    req = _require_purchase_request(db, request_id)
    if req.status != STATUS_AWAITING_PROFORMA:
        raise ValueError("فقط پس از تأیید مرحله اول درخواست، پیش‌فاکتور قابل ارسال است")

    row = db.get(ProcurementProforma, proforma_id)
    if not row or row.request_id != request_id:
        raise ValueError("پیش‌فاکتور یافت نشد")
    if row.status != PROFORMA_STATUS_DRAFT:
        raise ValueError("این پیش‌فاکتور قبلاً ارسال شده است")

    atts = list_attachments(db, ENTITY_PROCUREMENT_PROFORMA, row.id)
    if not atts:
        raise ValueError("فایل پیش‌فاکتور ضمیمه نشده است")

    row.status = PROFORMA_STATUS_SUBMITTED
    row.submitted_at = datetime.utcnow()
    req.status = STATUS_PROFORMA_REVIEW
    db.flush()

    from app.constants.procurement import WORKFLOW_REF_PURCHASE
    from app.services.procurement.purchase_workflow import (
        ACTION_UPLOAD_PROFORMA,
        complete_operational_step,
        get_active_purchase_workflow,
        repair_stuck_purchase_operational_steps,
    )

    active = get_active_purchase_workflow(db, request_id)
    if active and active.ref_type == WORKFLOW_REF_PURCHASE:
        try:
            complete_operational_step(
                db,
                request_id=request_id,
                user_or_id=user_id,
                expected_action=ACTION_UPLOAD_PROFORMA,
            )
        except ValueError:
            if not repair_stuck_purchase_operational_steps(db, request_id):
                db.rollback()
                raise
    else:
        db.commit()
        wf_payload = {
            "ref_type": WORKFLOW_REF_PROFORMA,
            "ref_id": request_id,
            "submitter_id": user_id,
            "proforma_id": proforma_id,
        }
        try:
            start_workflow_instance(db, wf_payload, sync_notify=True)
        except ValueError:
            db.rollback()
            raise
        publish_event("workflow.start", wf_payload)

    db.refresh(row)
    return serialize_proforma(db, row)


def mark_proforma_workflow_approved(
    db: Session,
    request_id: int,
    proforma_id: int | None,
    *,
    payment_method: str | None = None,
    payment_comment: str | None = None,
    payment_location: str | None = None,
    check_plan: list | None = None,
    payer_company_account_id: int | None = None,
) -> None:
    req = db.get(Request, request_id)
    if not req:
        return
    if proforma_id:
        row = db.get(ProcurementProforma, proforma_id)
        if row:
            row.status = PROFORMA_STATUS_APPROVED
    else:
        row = (
            db.query(ProcurementProforma)
            .filter(
                ProcurementProforma.request_id == request_id,
                ProcurementProforma.status == PROFORMA_STATUS_SUBMITTED,
            )
            .order_by(ProcurementProforma.id.desc())
            .first()
        )
        if row:
            row.status = PROFORMA_STATUS_APPROVED
    req.approved_payment_method = (payment_method or "").strip() or None
    req.approved_payment_comment = (payment_comment or "").strip() or None
    if payment_location is not None:
        req.payment_location = (payment_location or "").strip() or None
    if check_plan is not None:
        req.check_plan = check_plan
    if payer_company_account_id is not None:
        req.payer_company_account_id = (
            int(payer_company_account_id) if payer_company_account_id else None
        )
    req.status = STATUS_AWAITING_INVOICE
    db.flush()
    if row:
        from app.services.procurement.purchase_order_service import (
            ensure_purchase_order_for_request,
        )

        try:
            if row.supplier_id:
                ensure_purchase_order_for_request(db, request_id, row.supplier_id)
        except ValueError:
            pass
    db.commit()

    from app.services.procurement.procurement_notifications import (
        notify_after_proforma_ceo_approved,
    )

    notify_after_proforma_ceo_approved(
        db,
        request_id=request_id,
        payment_method=req.approved_payment_method,
        payment_comment=req.approved_payment_comment,
    )


def archive_proforma(db: Session, proforma_id: int) -> dict:
    row = db.get(ProcurementProforma, proforma_id)
    if not row:
        raise ValueError("پیش‌فاکتور یافت نشد")
    row.archived_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return serialize_proforma(db, row)
