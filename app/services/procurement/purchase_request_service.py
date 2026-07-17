"""درخواست خرید (purchase) — ثبت، سریالایز، workflow مرحله ۱."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.procurement import (
    REQUEST_TYPE_PURCHASE,
    STATUS_AWAITING_PROFORMA,
    STATUS_PAYMENT_PENDING,
    STATUS_PENDING,
    STATUS_PROFORMA_REVIEW,
    STATUS_RECEIVING,
    WORKFLOW_REF_PROFORMA,
    WORKFLOW_REF_PURCHASE,
    WORKFLOW_REF_REQUEST,
)
from app.infrastructure.messaging.publisher import publish_event
from app.models.item import Item
from app.models.procurement.purchase_order import PurchaseOrder
from app.models.request import Request
from app.models.request_item import RequestItem
from app.models.role import Role
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.schemas.procurement import CreatePurchaseRequestInput, PurchaseLineInput
from app.services.procurement.proforma_service import mark_proforma_workflow_approved
from app.services.procurement.procurement_payment_service import get_procurement_payment_summary
from app.services.crud_utils import ensure_editable
from app.services.workflow_lock import ensure_workflow_mutable_for_entity
from app.services.purchase_request_list_scope import (
    apply_purchase_request_list_scope,
    assert_purchase_scope_allowed,
)
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort
from app.constants.role_labels import role_display_name
from app.services.workflow_definition_service import assert_workflow_assignees_ready
from app.services.workflow_start import start_workflow_instance
from app.services.attachment_service import (
    ENTITY_PROCUREMENT_INVOICE,
    ENTITY_PROCUREMENT_REQUEST,
    delete_entity_attachment,
    list_attachments_serialized,
    save_entity_attachment,
    serialize_attachment,
)
from app.services.workflow_step_config import get_step_display_label

_ACTIVE_WORKFLOW_STATUSES = ("pending", "in_progress", "active")


def _latest_workflow_instance(
    db: Session, *, ref_type: str, ref_id: int
) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == ref_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def _serialize_workflow_instance_progress(
    db: Session, *, phase_key: str, ref_type: str, inst: WorkflowInstance
) -> dict:
    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.instance_id == inst.id)
        .order_by(WorkflowStep.order)
        .all()
    )
    step_items: list[dict] = []
    for step in steps:
        role = db.get(Role, step.role_id) if step.role_id else None
        role_label = (
            role_display_name(role.name, getattr(role, "display_name", None))
            if role
            else None
        )
        assignee = db.get(User, step.assigned_user_id) if step.assigned_user_id else None
        step_items.append(
            {
                "order": step.order,
                "label": get_step_display_label(
                    db, ref_type, step.order, role_name=role_label
                ),
                "status": step.status,
                "role": role.name if role else None,
                "assigned_user_name": assignee.full_name if assignee else None,
            }
        )
    return {
        "phase": phase_key,
        "instance_id": inst.id,
        "instance_status": inst.status,
        "steps": step_items,
    }


def get_purchase_workflow_progress(db: Session, request_id: int) -> list[dict]:
    from app.services.procurement.purchase_workflow import get_primary_purchase_workflow

    unified = get_primary_purchase_workflow(db, request_id)
    if unified and unified.ref_type == WORKFLOW_REF_PURCHASE:
        return [
            _serialize_workflow_instance_progress(
                db, phase_key="purchase", ref_type=WORKFLOW_REF_PURCHASE, inst=unified
            )
        ]

    out: list[dict] = []
    for phase_key, ref_type in (
        ("phase1", WORKFLOW_REF_REQUEST),
        ("phase2", WORKFLOW_REF_PROFORMA),
    ):
        inst = _latest_workflow_instance(db, ref_type=ref_type, ref_id=request_id)
        if not inst:
            continue
        out.append(
            _serialize_workflow_instance_progress(
                db, phase_key=phase_key, ref_type=ref_type, inst=inst
            )
        )
    return out


def sync_purchase_request_status_from_workflow(db: Session, request_id: int) -> bool:
    """اگر گردش‌کار تأیید شده ولی وضعیت درخواست به‌روز نشده، همگام‌سازی می‌کند."""
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        return False
    changed = False

    from app.services.procurement.purchase_workflow import (
        repair_stuck_purchase_operational_steps,
    )

    if repair_stuck_purchase_operational_steps(db, request_id):
        changed = True
        db.refresh(req)

    inst_phase1 = _latest_workflow_instance(
        db, ref_type=WORKFLOW_REF_REQUEST, ref_id=request_id
    )
    if inst_phase1 and inst_phase1.status == "approved" and req.status == STATUS_PENDING:
        mark_request_phase1_approved(db, request_id)
        changed = True
        db.refresh(req)

    inst_phase2 = _latest_workflow_instance(
        db, ref_type=WORKFLOW_REF_PROFORMA, ref_id=request_id
    )
    if (
        inst_phase2
        and inst_phase2.status == "approved"
        and req.status == STATUS_PROFORMA_REVIEW
    ):
        mark_proforma_workflow_approved(db, request_id, None)
        changed = True
        db.refresh(req)

    if req.payment_request_id and req.status == STATUS_PAYMENT_PENDING:
        pay_inst = _latest_workflow_instance(
            db, ref_type="payment_request", ref_id=req.payment_request_id
        )
        if pay_inst and pay_inst.status == "approved":
            from app.services.procurement.procurement_payment_service import (
                on_procurement_payment_workflow_approved,
            )

            on_procurement_payment_workflow_approved(db, req.payment_request_id)
            changed = True

    return changed


def _active_workflow_instance_id(db: Session, request_id: int, status: str) -> int | None:
    """نمونهٔ فعال گردش‌کار (مرحلهٔ جاری)."""
    from app.services.procurement.purchase_workflow import get_active_purchase_workflow

    inst = get_active_purchase_workflow(db, request_id)
    if inst:
        return inst.id

    def _latest_active(ref_type: str) -> WorkflowInstance | None:
        row = _latest_workflow_instance(db, ref_type=ref_type, ref_id=request_id)
        if row and row.status in _ACTIVE_WORKFLOW_STATUSES:
            return row
        return None

    if status == STATUS_PROFORMA_REVIEW:
        legacy = _latest_active(WORKFLOW_REF_PROFORMA)
        if legacy:
            return legacy.id

    legacy_req = _latest_active(WORKFLOW_REF_REQUEST)
    if legacy_req:
        return legacy_req.id

    row = _latest_workflow_instance(db, ref_type=WORKFLOW_REF_PURCHASE, ref_id=request_id)
    if not row:
        row = _latest_workflow_instance(db, ref_type=WORKFLOW_REF_REQUEST, ref_id=request_id)
    return row.id if row else None


def _resolve_line_fields(db: Session, line: PurchaseLineInput) -> tuple[int | None, str]:
    item_id = line.item_id
    item_name = line.item_name.strip()
    if item_id:
        item = db.get(Item, item_id)
        if item:
            return item.id, item.name
    if not item_name:
        raise ValueError("نام کالا یا انتخاب از لیست کالا الزامی است")
    return item_id, item_name


def serialize_purchase_request(db: Session, req: Request) -> dict:
    requester = db.get(User, req.requester_id)
    lines = (
        db.query(RequestItem).filter(RequestItem.request_id == req.id).order_by(RequestItem.id).all()
    )
    po_summary = None
    if req.purchase_order_id:
        po = db.get(PurchaseOrder, req.purchase_order_id)
        if po:
            po_summary = {
                "id": po.id,
                "order_no": po.order_no,
                "status": po.status,
            }
    return {
        "id": req.id,
        "type": req.type,
        "status": req.status,
        "requester_id": req.requester_id,
        "requester_name": (requester.full_name or requester.username) if requester else None,
        "reason": req.reason,
        "payment_request_id": req.payment_request_id,
        "purchase_order_id": req.purchase_order_id,
        "payment": get_procurement_payment_summary(db, req),
        "purchase_order": po_summary,
        "items": [
            {
                "id": li.id,
                "item_name": li.item_name,
                "quantity": li.quantity,
                "description": li.description,
                "item_id": li.item_id,
            }
            for li in lines
        ],
        "workflow_instance_id": _active_workflow_instance_id(db, req.id, req.status),
        "attachments": list_attachments_serialized(
            db, ENTITY_PROCUREMENT_REQUEST, req.id
        ),
        "invoices": list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, req.id),
        "approved_payment_method": req.approved_payment_method,
        "approved_payment_comment": req.approved_payment_comment,
        "invoice_paid_at": req.invoice_paid_at.isoformat() if req.invoice_paid_at else None,
        "created_at": req.created_at,
    }


async def upload_purchase_request_attachment(
    db: Session,
    *,
    request_id: int,
    user,
    file,
) -> dict:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        raise ValueError("request not found")
    if req.requester_id != user.id:
        from app.services.workflow_lock import user_may_bypass_workflow_edit_lock

        if not user_may_bypass_workflow_edit_lock(user):
            raise ValueError("access denied")
    att = await save_entity_attachment(
        db,
        entity_type=ENTITY_PROCUREMENT_REQUEST,
        entity_id=request_id,
        uploaded_by_id=user.id,
        file=file,
    )
    return serialize_attachment(att)


def delete_purchase_request_attachment(
    db: Session, *, request_id: int, attachment_id: int, user
) -> None:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        raise ValueError("request not found")
    if req.requester_id != user.id:
        raise ValueError("access denied")
    if not delete_entity_attachment(
        db,
        entity_type=ENTITY_PROCUREMENT_REQUEST,
        entity_id=request_id,
        attachment_id=attachment_id,
    ):
        raise ValueError("attachment not found")


def create_purchase_request(
    db: Session,
    *,
    user_id: int,
    payload: CreatePurchaseRequestInput,
) -> dict:
    req = Request(
        requester_id=user_id,
        type=REQUEST_TYPE_PURCHASE,
        status=STATUS_PENDING,
        warehouse_id=None,
        reason=(payload.reason or "").strip() or None,
    )
    db.add(req)
    db.flush()

    for line in payload.lines:
        item_id, item_name = _resolve_line_fields(db, line)
        db.add(
            RequestItem(
                request_id=req.id,
                item_id=item_id,
                item_name=item_name,
                quantity=line.quantity,
                description=(line.description or "").strip() or None,
            )
        )

    db.commit()
    db.refresh(req)

    wf_payload: dict = {
        "ref_type": WORKFLOW_REF_PURCHASE,
        "ref_id": req.id,
        "submitter_id": user_id,
    }
    if payload.assignees_by_order:
        wf_payload["assignees_by_order"] = payload.assignees_by_order

    try:
        assert_workflow_assignees_ready(
            db, WORKFLOW_REF_PURCHASE, submitter_id=user_id
        )
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        db.rollback()
        raise
    publish_event("workflow.start", wf_payload)

    return serialize_purchase_request(db, req)


def mark_request_phase1_approved(db: Session, request_id: int) -> None:
    req = db.get(Request, request_id)
    if not req:
        return
    req.status = STATUS_AWAITING_PROFORMA
    db.commit()
    from app.services.procurement.procurement_notifications import (
        notify_purchase_team_proforma_needed,
    )

    notify_purchase_team_proforma_needed(db, request_id)


def get_purchase_request_detail(db: Session, request_id: int) -> dict | None:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        return None
    sync_purchase_request_status_from_workflow(db, request_id)
    db.refresh(req)
    data = serialize_purchase_request(db, req)
    data["workflow_progress"] = get_purchase_workflow_progress(db, request_id)
    return data


def get_purchase_request_detail_for_viewer(
    db: Session, request_id: int, user
) -> dict | None:
    """خواندن جزئیات برای ثبت‌کننده، تدارکات، یا تأییدکنندهٔ workflow."""
    from app.services.permission import user_has_permission_db
    from app.services.purchase_request_list_scope import user_can_access_purchase_request

    if user_has_permission_db(db, user.id, "procurement.read"):
        return get_purchase_request_detail(db, request_id)
    if user_can_access_purchase_request(db, user, request_id):
        return get_purchase_request_detail(db, request_id)
    raise ValueError("access denied")


def get_purchase_request_by_instance_detail(db: Session, user, instance_id: int) -> dict:
    from app.models.workflow_instance import WorkflowInstance
    from app.services.procurement.purchase_workflow import is_purchase_workflow_ref

    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        raise ValueError("workflow instance not found")
    if not is_purchase_workflow_ref(inst.ref_type):
        raise ValueError("این نمونه workflow مربوط به درخواست خرید نیست")
    data = get_purchase_request_detail_for_viewer(db, int(inst.ref_id), user)
    if not data:
        raise ValueError(
            f"درخواست خرید با شناسه {inst.ref_id} یافت نشد؛ "
            "احتمالاً رکورد حذف شده یا داده ناسازگار است."
        )
    data["workflow_instance_id"] = instance_id
    return data


def list_purchase_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> list[dict]:
    resolved = assert_purchase_scope_allowed(db, viewer, scope)
    query = db.query(Request).filter(Request.type == REQUEST_TYPE_PURCHASE)
    query = apply_purchase_request_list_scope(db, query, user=viewer, scope=resolved)
    query = apply_equal_filter(query, Request, filter_by, filter_value)
    query = apply_search_filter(query, Request, search, ["status", "reason"])
    resolved_sort = sort_by if hasattr(Request, sort_by) else "created_at"
    query = apply_sort(query, Request, resolved_sort, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [serialize_purchase_request(db, r) for r in rows]


def count_purchase_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    resolved = assert_purchase_scope_allowed(db, viewer, scope)
    query = db.query(func.count(Request.id)).filter(Request.type == REQUEST_TYPE_PURCHASE)
    query = apply_purchase_request_list_scope(db, query, user=viewer, scope=resolved)
    query = apply_equal_filter(query, Request, filter_by, filter_value)
    query = apply_search_filter(query, Request, search, ["status", "reason"])
    return query.scalar() or 0


def update_purchase_request_lines(
    db: Session,
    request_id: int,
    *,
    user_id: int,
    lines: list[PurchaseLineInput],
    reason: str | None = None,
    actor=None,
) -> dict:
    req = db.get(Request, request_id)
    if not req:
        raise ValueError("request not found")
    from app.models.user import User
    from app.services.workflow_lock import user_may_bypass_workflow_edit_lock

    editor = actor if actor is not None else db.get(User, user_id)
    if editor is None:
        raise ValueError("access denied")
    if req.requester_id != editor.id and not user_may_bypass_workflow_edit_lock(editor):
        raise ValueError("access denied")
    ensure_editable(req)
    ensure_workflow_mutable_for_entity(
        db,
        ref_type=WORKFLOW_REF_REQUEST,
        ref_id=request_id,
        user=editor,
    )
    if reason is not None:
        req.reason = reason.strip() or None
    db.query(RequestItem).filter_by(request_id=request_id).delete()
    for line in lines:
        item_id, item_name = _resolve_line_fields(db, line)
        db.add(
            RequestItem(
                request_id=request_id,
                item_id=item_id,
                item_name=item_name,
                quantity=line.quantity,
                description=(line.description or "").strip() or None,
            )
        )
    db.commit()
    db.refresh(req)
    return serialize_purchase_request(db, req)
