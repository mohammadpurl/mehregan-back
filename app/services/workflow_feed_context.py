"""متن و متادیتای غنی برای اعلان‌ها و کارتابل workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.payment_request import PaymentRequest
from app.models.financial_document import FinancialDocument
from app.models.petty_cash_request import PettyCashRequest
from app.models.mission_request import MissionRequest
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.services.workflow_messages import (
    inbox_message_for_step,
    inbox_title_for_step,
    notification_message_for_step,
    notification_title_for_step,
    ref_type_label,
)

PAYMENT_TYPE_LABELS: dict[str, str] = {
    "loan": "وام",
    "advance": "مساعده",
    "payment_order": "دستور پرداخت",
}


def datetime_to_iso_utc(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


@dataclass
class WorkflowNotifyContext:
    ref_type: str
    ref_type_label: str
    detail_label: str
    business_ref_id: int | None
    request_created_at: datetime | None
    amount: float | None
    requester_name: str | None
    step_order: int | None = None

    @property
    def display_label(self) -> str:
        return self.detail_label or self.ref_type_label


def _user_display_name(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def _context_from_instance(
    inst: WorkflowInstance,
    *,
    step_order: int | None = None,
    payments: dict[int, PaymentRequest] | None = None,
    petties: dict[int, PettyCashRequest] | None = None,
    missions: dict[int, MissionRequest] | None = None,
    financial_docs: dict[int, FinancialDocument] | None = None,
    users: dict[int, User] | None = None,
) -> WorkflowNotifyContext:
    ref_type = (inst.ref_type or "").strip()
    base_label = ref_type_label(ref_type)
    detail_label = base_label
    business_ref_id = inst.ref_id
    request_created_at: datetime | None = None
    amount: float | None = None
    requester_name: str | None = None

    if ref_type in ("payment_request", "payment_order") and inst.ref_id:
        pr = (payments or {}).get(int(inst.ref_id))
        if pr:
            pt = (pr.payment_type or "").strip().lower()
            detail_label = PAYMENT_TYPE_LABELS.get(pt, base_label)
            request_created_at = pr.created_at or request_created_at
            amount = float(pr.amount) if pr.amount is not None else None
            requester_name = _user_display_name(
                (users or {}).get(pr.requester_id) if users is not None else None
            )
    elif ref_type == "petty_cash" and inst.ref_id:
        pc = (petties or {}).get(inst.ref_id) if petties is not None else None
        if pc:
            detail_label = "تنخواه"
            request_created_at = pc.created_at or request_created_at
            amount = float(pc.amount) if pc.amount is not None else None
            requester_name = _user_display_name(
                (users or {}).get(pc.requester_id) if users is not None else None
            )
    elif ref_type == "mission_request" and inst.ref_id:
        mr = (missions or {}).get(inst.ref_id) if missions is not None else None
        if mr:
            detail_label = "درخواست ماموریت"
            request_created_at = mr.created_at or request_created_at
            requester_name = _user_display_name(
                (users or {}).get(mr.requester_id) if users is not None else None
            )
    elif ref_type == "financial_document" and inst.ref_id:
        fd = (financial_docs or {}).get(int(inst.ref_id)) if financial_docs is not None else None
        if fd:
            detail_label = "سند مالی"
            if (fd.document_type or "").strip().lower() == "check":
                detail_label = "چک / سند مالی"
            request_created_at = fd.created_at or request_created_at
            amount = float(fd.amount) if fd.amount is not None else None
            requester_name = _user_display_name(
                (users or {}).get(fd.requester_id) if users is not None else None
            )

    return WorkflowNotifyContext(
        ref_type=ref_type,
        ref_type_label=base_label,
        detail_label=detail_label,
        business_ref_id=business_ref_id,
        request_created_at=request_created_at,
        amount=amount,
        requester_name=requester_name,
        step_order=step_order,
    )


def batch_load_workflow_contexts(
    db: Session,
    instance_ids: list[int],
    *,
    step_orders: dict[int, int | None] | None = None,
) -> dict[int, WorkflowNotifyContext]:
    """بارگذاری یکجای context برای چند نمونه workflow (جلوگیری از N+1)."""
    unique_ids = list({int(i) for i in instance_ids if i})
    if not unique_ids:
        return {}

    instances = (
        db.query(WorkflowInstance).filter(WorkflowInstance.id.in_(unique_ids)).all()
    )
    payment_ids: list[int] = []
    petty_ids: list[int] = []
    mission_ids: list[int] = []
    financial_doc_ids: list[int] = []
    for inst in instances:
        rt = (inst.ref_type or "").strip()
        if rt in ("payment_request", "payment_order") and inst.ref_id:
            payment_ids.append(int(inst.ref_id))
        elif rt == "petty_cash" and inst.ref_id:
            petty_ids.append(int(inst.ref_id))
        elif rt == "mission_request" and inst.ref_id:
            mission_ids.append(int(inst.ref_id))
        elif rt == "financial_document" and inst.ref_id:
            financial_doc_ids.append(int(inst.ref_id))

    payments: dict[int, PaymentRequest] = {}
    if payment_ids:
        for row in (
            db.query(PaymentRequest).filter(PaymentRequest.id.in_(payment_ids)).all()
        ):
            payments[int(row.id)] = row

    petties: dict[int, PettyCashRequest] = {}
    if petty_ids:
        for row in (
            db.query(PettyCashRequest).filter(PettyCashRequest.id.in_(petty_ids)).all()
        ):
            petties[int(row.id)] = row

    missions: dict[int, MissionRequest] = {}
    if mission_ids:
        for row in (
            db.query(MissionRequest).filter(MissionRequest.id.in_(mission_ids)).all()
        ):
            missions[int(row.id)] = row

    financial_docs: dict[int, FinancialDocument] = {}
    if financial_doc_ids:
        for row in (
            db.query(FinancialDocument)
            .filter(FinancialDocument.id.in_(financial_doc_ids))
            .all()
        ):
            financial_docs[int(row.id)] = row

    user_ids: set[int] = set()
    for pr in payments.values():
        if pr.requester_id:
            user_ids.add(int(pr.requester_id))
    for pc in petties.values():
        if pc.requester_id:
            user_ids.add(int(pc.requester_id))
    for mr in missions.values():
        if mr.requester_id:
            user_ids.add(int(mr.requester_id))
    for fd in financial_docs.values():
        if fd.requester_id:
            user_ids.add(int(fd.requester_id))

    users: dict[int, User] = {}
    if user_ids:
        for row in db.query(User).filter(User.id.in_(user_ids)).all():
            users[int(row.id)] = row

    out: dict[int, WorkflowNotifyContext] = {}
    for inst in instances:
        step_order = step_orders.get(inst.id) if step_orders else None
        out[inst.id] = _context_from_instance(
            inst,
            step_order=step_order,
            payments=payments,
            petties=petties,
            missions=missions,
            financial_docs=financial_docs,
            users=users,
        )
    return out


def build_workflow_notify_context(
    db: Session,
    inst: WorkflowInstance | None,
    *,
    step_order: int | None = None,
) -> WorkflowNotifyContext | None:
    if not inst:
        return None

    ref_type = (inst.ref_type or "").strip()
    base_label = ref_type_label(ref_type)
    detail_label = base_label
    business_ref_id = inst.ref_id
    request_created_at: datetime | None = None
    amount: float | None = None
    requester_name: str | None = None

    if ref_type in ("payment_request", "payment_order") and inst.ref_id:
        pr = db.get(PaymentRequest, inst.ref_id)
        if pr:
            if ref_type == "payment_order":
                kind = (pr.payment_order_kind or "individual").strip().lower()
                detail_label = (
                    "دستور پرداخت جمعی"
                    if kind == "collective"
                    else "دستور پرداخت انفرادی"
                )
            else:
                pt = (pr.payment_type or "").strip().lower()
                detail_label = PAYMENT_TYPE_LABELS.get(pt, base_label)
            request_created_at = pr.created_at or request_created_at
            amount = float(pr.amount) if pr.amount is not None else None
            requester_name = _user_display_name(db.get(User, pr.requester_id))
    elif ref_type == "petty_cash" and inst.ref_id:
        pc = db.get(PettyCashRequest, inst.ref_id)
        if pc:
            detail_label = "تنخواه"
            request_created_at = pc.created_at or request_created_at
            amount = float(pc.amount) if pc.amount is not None else None
            requester_name = _user_display_name(db.get(User, pc.requester_id))
    elif ref_type == "mission_request" and inst.ref_id:
        mr = db.get(MissionRequest, inst.ref_id)
        if mr:
            detail_label = "درخواست ماموریت"
            request_created_at = mr.created_at or request_created_at
            requester_name = _user_display_name(db.get(User, mr.requester_id))
    elif ref_type == "financial_document" and inst.ref_id:
        fd = db.get(FinancialDocument, inst.ref_id)
        if fd:
            detail_label = "سند مالی"
            if (fd.document_type or "").strip().lower() == "check":
                detail_label = "چک / سند مالی"
            request_created_at = fd.created_at or request_created_at
            amount = float(fd.amount) if fd.amount is not None else None
            requester_name = _user_display_name(db.get(User, fd.requester_id))

    return WorkflowNotifyContext(
        ref_type=ref_type,
        ref_type_label=base_label,
        detail_label=detail_label,
        business_ref_id=business_ref_id,
        request_created_at=request_created_at,
        amount=amount,
        requester_name=requester_name,
        step_order=step_order,
    )


def context_to_meta(ctx: WorkflowNotifyContext, workflow_instance_id: int) -> dict:
    return {
        "workflowInstanceId": workflow_instance_id,
        "businessRefType": ctx.ref_type,
        "businessRefId": ctx.business_ref_id,
        "requestTypeLabel": ctx.detail_label,
        "requestCreatedAt": datetime_to_iso_utc(ctx.request_created_at),
        "requestAmount": ctx.amount,
        "requesterName": ctx.requester_name,
        "stepOrder": ctx.step_order,
    }


def enrich_workflow_feed_fields(
    db: Session,
    *,
    workflow_instance_id: int | None,
    title: str,
    message: str | None,
    step_order: int | None = None,
    for_inbox: bool = False,
) -> dict:
    """فیلدهای اضافه + بازنویسی عنوان/پیام برای نمایش در UI."""
    if not workflow_instance_id:
        return {}
    inst = db.get(WorkflowInstance, workflow_instance_id)
    ctx = build_workflow_notify_context(db, inst, step_order=step_order)
    if not ctx:
        return {}

    extra = context_to_meta(ctx, workflow_instance_id)
    if for_inbox:
        extra["title"] = inbox_title_for_step(ctx=ctx, step_order=step_order)
        extra["message"] = inbox_message_for_step(ctx=ctx, step_order=step_order)
    else:
        extra["title"] = notification_title_for_step(ctx=ctx)
        extra["message"] = notification_message_for_step(ctx=ctx, step_order=step_order)
    return extra
