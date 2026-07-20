"""پیوست‌های مخصوص هر مرحله گردش‌کار (جدا از پیوست‌های اصلی درخواست)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import ROOT_PATH, UPLOAD_DIRECTORY
from app.constants.upload_limits import ATTACHMENT_ALLOWED_EXTENSIONS, MAX_ATTACHMENT_BYTES
from app.models.attachment import Attachment
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.attachment_service import serialize_attachment
from app.services.workflow_attachment_access import ENTITY_WORKFLOW_STEP
from app.services.workflow_step_access import user_can_act_on_workflow_step


def _upload_dir() -> Path:
    base = Path(UPLOAD_DIRECTORY) / "workflow_steps"
    base.mkdir(parents=True, exist_ok=True)
    return base


def upload_step_attachment(
    db: Session,
    *,
    instance_id: int,
    step_id: int,
    user,
    file: UploadFile,
) -> dict:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")

    step = db.get(WorkflowStep, step_id)
    if not step or step.instance_id != instance_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="step not found")

    if step.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فقط در مرحله در انتظار تأیید می‌توان پیوست گذاشت",
        )

    if not user_can_act_on_workflow_step(user, step):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="access denied")

    # اسناد مالی: فقط پیوست روی خود سند (entity) — نه روی مرحله workflow
    if inst.ref_type == "financial_document":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "برای اسناد مالی، تصویر را از صفحه سند مالی آپلود کنید "
                "(فقط کارشناس مالی ثبت‌کننده)"
            ),
        )

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file required")

    suffix = Path(file.filename).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in ATTACHMENT_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ATTACHMENT_ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"نوع فایل مجاز نیست. مجاز: {allowed}",
        )

    content = file.file.read()
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="حجم فایل بیش از حد مجاز است")

    safe_name = Path(file.filename).name
    stored = f"{uuid4().hex}_{safe_name}"
    rel = f"workflow_steps/{instance_id}/{step_id}/{stored}"
    dest = Path(UPLOAD_DIRECTORY) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    row = Attachment(
        file_name=safe_name,
        file_path=rel.replace("\\", "/"),
        entity_type=ENTITY_WORKFLOW_STEP,
        entity_id=step_id,
        uploaded_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    payload = serialize_attachment(row)
    payload["workflowInstanceId"] = instance_id
    payload["workflowStepId"] = step_id
    payload["stepOrder"] = step.order
    return payload


def _append_serialized(
    out: list[dict],
    *,
    instance_id: int,
    rows: list[dict],
    step_order: int | None,
    workflow_step_id: int | None,
    scope: str,
) -> None:
    for row in rows:
        item = dict(row)
        item["workflowInstanceId"] = instance_id
        item["workflowStepId"] = workflow_step_id
        item["stepOrder"] = step_order
        item["attachmentScope"] = scope
        out.append(item)


def collect_plan_attachments(db: Session, instance_id: int) -> list[dict]:
    """پیوست‌های مراحل workflow + پیوست‌های درخواست/پیش‌فاکتور مرتبط."""
    from app.constants.procurement import WORKFLOW_REF_PROFORMA
    from app.services.procurement.purchase_workflow import is_purchase_workflow_ref
    from app.models.procurement.proforma import ProcurementProforma
    from app.services.attachment_service import (
        ENTITY_PROCUREMENT_INVOICE,
        ENTITY_PROCUREMENT_PAYMENT_SLIP,
        ENTITY_PROCUREMENT_PROFORMA,
        ENTITY_PROCUREMENT_REQUEST,
        list_attachments_serialized,
    )

    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return []

    out: list[dict] = []
    out.extend(list_instance_step_attachments(db, instance_id))
    for item in out:
        item.setdefault("attachmentScope", "workflow_step")

    if is_purchase_workflow_ref(inst.ref_type) and inst.ref_id:
        request_id = int(inst.ref_id)
        _append_serialized(
            out,
            instance_id=instance_id,
            rows=list_attachments_serialized(db, ENTITY_PROCUREMENT_REQUEST, request_id),
            step_order=0,
            workflow_step_id=None,
            scope="request",
        )
        proformas = (
            db.query(ProcurementProforma)
            .filter(ProcurementProforma.request_id == request_id)
            .order_by(ProcurementProforma.id.asc())
            .all()
        )
        for pf in proformas:
            _append_serialized(
                out,
                instance_id=instance_id,
                rows=list_attachments_serialized(db, ENTITY_PROCUREMENT_PROFORMA, pf.id),
                step_order=None,
                workflow_step_id=None,
                scope="proforma",
            )
        _append_serialized(
            out,
            instance_id=instance_id,
            rows=list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id),
            step_order=5,
            workflow_step_id=None,
            scope="invoice",
        )
        _append_serialized(
            out,
            instance_id=instance_id,
            rows=list_attachments_serialized(
                db, ENTITY_PROCUREMENT_PAYMENT_SLIP, request_id
            ),
            step_order=6,
            workflow_step_id=None,
            scope="payment_slip",
        )

    if inst.ref_type == WORKFLOW_REF_PROFORMA and inst.ref_id:
        _append_serialized(
            out,
            instance_id=instance_id,
            rows=list_attachments_serialized(db, ENTITY_PROCUREMENT_PROFORMA, int(inst.ref_id)),
            step_order=0,
            workflow_step_id=None,
            scope="proforma",
        )

    return out


def list_instance_step_attachments(db: Session, instance_id: int) -> list[dict]:
    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.instance_id == instance_id)
        .order_by(WorkflowStep.order)
        .all()
    )
    step_ids = [s.id for s in steps]
    if not step_ids:
        return []

    rows = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == ENTITY_WORKFLOW_STEP,
            Attachment.entity_id.in_(step_ids),
        )
        .order_by(Attachment.id.asc())
        .all()
    )
    order_by_step = {s.id: s.order for s in steps}
    out: list[dict] = []
    for row in rows:
        item = serialize_attachment(row)
        item["workflowInstanceId"] = instance_id
        item["workflowStepId"] = row.entity_id
        item["stepOrder"] = order_by_step.get(row.entity_id)
        out.append(item)
    return out
