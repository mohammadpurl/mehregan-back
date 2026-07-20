"""پیوست‌های درخواست‌ها (پرداخت، تنخواه، …) با دانلود امن."""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import API_PUBLIC_BASE_URL, ROOT_PATH, UPLOAD_DIRECTORY
from app.constants.upload_limits import (
    ATTACHMENT_ALLOWED_EXTENSIONS,
    MAX_ATTACHMENT_BYTES,
)
from app.models.attachment import Attachment

ENTITY_PAYMENT_REQUEST = "payment_request"
ENTITY_PETTY_CASH = "petty_cash"
ENTITY_FINANCIAL_DOCUMENT = "financial_document"
ENTITY_PROCUREMENT_REQUEST = "procurement_request"
ENTITY_PROCUREMENT_PROFORMA = "procurement_proforma"
ENTITY_PROCUREMENT_INVOICE = "procurement_invoice"
ENTITY_PROCUREMENT_PAYMENT_SLIP = "procurement_payment_slip"
ENTITY_PROCUREMENT_BOL = "procurement_bol"
ENTITY_GOODS_RECEIPT = "goods_receipt"
ENTITY_AD_HOC_TASK = "ad_hoc_task"
ENTITY_AD_HOC_TASK_STEP = "ad_hoc_task_step"
ENTITY_MISSION_REQUEST = "mission_request"

ENTITY_UPLOAD_DIRS: dict[str, str] = {
    ENTITY_PAYMENT_REQUEST: "payment_requests",
    ENTITY_PETTY_CASH: "petty_cash",
    ENTITY_FINANCIAL_DOCUMENT: "financial_documents",
    ENTITY_PROCUREMENT_REQUEST: "procurement_requests",
    ENTITY_PROCUREMENT_PROFORMA: "procurement_proformas",
    ENTITY_PROCUREMENT_INVOICE: "procurement_invoices",
    ENTITY_PROCUREMENT_PAYMENT_SLIP: "procurement_payment_slips",
    ENTITY_PROCUREMENT_BOL: "procurement_bols",
    ENTITY_GOODS_RECEIPT: "goods_receipts",
    ENTITY_AD_HOC_TASK: "ad_hoc_tasks",
    ENTITY_AD_HOC_TASK_STEP: "ad_hoc_task_steps",
    ENTITY_MISSION_REQUEST: "mission_requests",
}

ALLOWED_EXTENSIONS = set(ATTACHMENT_ALLOWED_EXTENSIONS)


def attachment_download_path(attachment_id: int) -> str:
    path = f"/attachments/{attachment_id}/download"
    if ROOT_PATH:
        return f"{ROOT_PATH}{path}"
    return path


def _absolute_file_url(public_path: str) -> str | None:
    if not public_path:
        return None
    base = (API_PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return None
    return f"{base}{public_path}"


def serialize_attachment(row: Attachment) -> dict:
    download = attachment_download_path(row.id)
    return {
        "id": row.id,
        "file_name": row.file_name,
        "url": download,
        "file_url": _absolute_file_url(download),
        "download_url": download,
        "uploaded_at": row.created_at,
    }


def list_attachments(
    db: Session, entity_type: str, entity_id: int
) -> list[Attachment]:
    return (
        db.query(Attachment)
        .filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(Attachment.id.asc())
        .all()
    )


def list_attachments_serialized(
    db: Session, entity_type: str, entity_id: int
) -> list[dict]:
    return [serialize_attachment(a) for a in list_attachments(db, entity_type, entity_id)]


def count_attachments_batch(
    db: Session, entity_type: str, entity_ids: list[int]
) -> dict[int, int]:
    if not entity_ids:
        return {}
    rows = (
        db.query(Attachment.entity_id, func.count(Attachment.id))
        .filter(
            Attachment.entity_type == entity_type,
            Attachment.entity_id.in_(entity_ids),
        )
        .group_by(Attachment.entity_id)
        .all()
    )
    return {int(eid): int(cnt) for eid, cnt in rows}


def list_attachments_batch(
    db: Session, entity_type: str, entity_ids: list[int]
) -> dict[int, list[Attachment]]:
    if not entity_ids:
        return {}
    rows = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == entity_type,
            Attachment.entity_id.in_(entity_ids),
        )
        .order_by(Attachment.entity_id.asc(), Attachment.id.asc())
        .all()
    )
    out: dict[int, list[Attachment]] = {eid: [] for eid in entity_ids}
    for row in rows:
        out.setdefault(row.entity_id, []).append(row)
    return out


def get_attachment(db: Session, attachment_id: int) -> Attachment | None:
    return db.get(Attachment, attachment_id)


def _allowed_attachment_path_prefixes() -> tuple[str, ...]:
    from app.services.workflow_attachment_access import WORKFLOW_STEP_UPLOAD_PREFIX

    return tuple(f"{d}/" for d in ENTITY_UPLOAD_DIRS.values()) + (
        WORKFLOW_STEP_UPLOAD_PREFIX,
    )


def resolve_attachment_file_path(att: Attachment) -> Path:
    rel = att.file_path.replace("\\", "/").lstrip("/")
    allowed = _allowed_attachment_path_prefixes()
    if ".." in rel or not rel.startswith(allowed):
        raise ValueError("مسیر فایل نامعتبر است")
    root = UPLOAD_DIRECTORY.resolve()
    full = (UPLOAD_DIRECTORY / rel).resolve()
    try:
        full.relative_to(root)
    except ValueError as exc:
        raise ValueError("مسیر فایل نامعتبر است") from exc
    if not full.is_file():
        raise ValueError("فایل پیوست روی دیسک یافت نشد")
    return full


def _upload_base_dir(entity_type: str, entity_id: int) -> Path:
    folder = ENTITY_UPLOAD_DIRS.get(entity_type)
    if not folder:
        raise ValueError("نوع موجودیت برای پیوست پشتیبانی نمی‌شود")
    path = UPLOAD_DIRECTORY / folder / str(entity_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_entity_attachment(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    uploaded_by_id: int,
    file: UploadFile,
) -> Attachment:
    if entity_type not in ENTITY_UPLOAD_DIRS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نوع موجودیت برای پیوست پشتیبانی نمی‌شود",
        )
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نام فایل نامعتبر است",
        )
    suffix = Path(file.filename).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"پسوند فایل مجاز نیست. مجاز: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    body = await file.read()
    if len(body) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"حجم فایل از {MAX_ATTACHMENT_BYTES // (1024 * 1024)} مگابایت بیشتر است",
        )

    safe_name = f"{uuid4().hex}{suffix}"
    dest_dir = _upload_base_dir(entity_type, entity_id)
    dest_path = dest_dir / safe_name
    dest_path.write_bytes(body)

    folder = ENTITY_UPLOAD_DIRS[entity_type]
    relative = f"{folder}/{entity_id}/{safe_name}"
    att = Attachment(
        file_name=file.filename[:250],
        file_path=relative,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_by=uploaded_by_id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def delete_attachment_file(db: Session, att: Attachment) -> None:
    rel = att.file_path.replace("\\", "/").lstrip("/")
    allowed = _allowed_attachment_path_prefixes()
    if ".." in rel or not rel.startswith(allowed):
        return
    root = UPLOAD_DIRECTORY.resolve()
    full = (UPLOAD_DIRECTORY / rel).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        return
    try:
        if full.is_file():
            full.unlink()
    except OSError:
        pass


def delete_entity_attachment(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    attachment_id: int,
) -> bool:
    att = db.get(Attachment, attachment_id)
    if not att or att.entity_type != entity_type or att.entity_id != entity_id:
        return False
    delete_attachment_file(db, att)
    db.delete(att)
    db.commit()
    return True


def delete_all_for_entity(db: Session, entity_type: str, entity_id: int) -> None:
    rows = list_attachments(db, entity_type, entity_id)
    for att in rows:
        delete_attachment_file(db, att)
        db.delete(att)
    db.commit()


def assert_user_can_access_attachment(db: Session, user, att: Attachment) -> None:
    from app.models.payment_request import PaymentRequest
    from app.models.petty_cash_request import PettyCashRequest
    from app.models.procurement.goods_receipt import GoodsReceipt
    from app.models.procurement.proforma import ProcurementProforma
    from app.services.payment_request import assert_payment_access
    from app.services.petty_cash import get_petty_cash
    from app.services.purchase_request_list_scope import user_can_access_purchase_request

    if att.entity_type == ENTITY_PAYMENT_REQUEST:
        pr = db.get(PaymentRequest, att.entity_id)
        assert_payment_access(db, user, pr)
        return
    if att.entity_type == ENTITY_PETTY_CASH:
        row = db.get(PettyCashRequest, att.entity_id)
        if not row:
            raise ValueError("درخواست تنخواه یافت نشد")
        get_petty_cash(db, att.entity_id, user)
        return
    if att.entity_type == ENTITY_MISSION_REQUEST:
        from app.services.mission_request import get_mission_request

        get_mission_request(db, att.entity_id, user)
        return
    if att.entity_type == ENTITY_FINANCIAL_DOCUMENT:
        from app.services.financial_document import get_financial_document

        get_financial_document(db, att.entity_id, user)
        return
    if att.entity_type == ENTITY_PROCUREMENT_PROFORMA:
        row = db.get(ProcurementProforma, att.entity_id)
        if not row:
            raise ValueError("پیش‌فاکتور یافت نشد")
        if user_can_access_purchase_request(db, user, row.request_id):
            return
        raise ValueError("access denied")
    if att.entity_type == ENTITY_GOODS_RECEIPT:
        grn = db.get(GoodsReceipt, att.entity_id)
        if not grn:
            raise ValueError("رسید انبار یافت نشد")
        if user_can_access_purchase_request(db, user, grn.request_id):
            return
        raise ValueError("access denied")
    if att.entity_type == ENTITY_PROCUREMENT_REQUEST:
        if user_can_access_purchase_request(db, user, att.entity_id):
            return
        raise ValueError("access denied")
    if att.entity_type == ENTITY_PROCUREMENT_INVOICE:
        if user_can_access_purchase_request(db, user, att.entity_id):
            return
        raise ValueError("access denied")
    if att.entity_type in (ENTITY_PROCUREMENT_PAYMENT_SLIP, ENTITY_PROCUREMENT_BOL):
        if user_can_access_purchase_request(db, user, att.entity_id):
            return
        raise ValueError("access denied")
    if att.entity_type == ENTITY_AD_HOC_TASK:
        from app.models.ad_hoc_task import AdHocTask
        from app.services.ad_hoc_task_service import user_can_access_task
        task = db.get(AdHocTask, att.entity_id)
        if task and user_can_access_task(db, task, user):
            return
        raise ValueError("access denied")
    if att.entity_type == ENTITY_AD_HOC_TASK_STEP:
        from app.models.ad_hoc_task import AdHocTask, AdHocTaskStep
        from app.services.ad_hoc_task_service import user_can_access_task

        step = db.get(AdHocTaskStep, att.entity_id)
        if not step:
            raise ValueError("مرحله یافت نشد")
        task = db.get(AdHocTask, step.task_id)
        if task and user_can_access_task(db, task, user):
            return
        raise ValueError("access denied")
    from app.services.workflow_attachment_access import (
        ENTITY_WORKFLOW_STEP,
        user_can_access_workflow_step_attachment,
    )

    if att.entity_type == ENTITY_WORKFLOW_STEP:
        if user_can_access_workflow_step_attachment(db, user, att):
            return
        raise ValueError("access denied")
    raise ValueError("access denied")
