from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.petty_cash import (
    EXPENSE_SOURCE_EXCEL,
    EXPENSE_SOURCE_MANUAL,
    SETTLEMENT_NONE,
    SETTLEMENT_PENDING,
    SETTLEMENT_PENDING_APPROVAL,
    SETTLEMENT_SETTLED,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
)
from app.infrastructure.messaging.publisher import publish_event
from app.models.petty_cash_expense import PettyCashExpenseLine
from app.models.petty_cash_request import PettyCashRequest
from app.models.user import User
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.services.workflow_definition_service import preview_assignees
from app.services.workflow_step_config import format_missing_role_assignee_error
from app.schemas.petty_cash import PettyCashExpenseLineIn
from app.services.petty_cash_excel import parse_expense_excel
from app.services.query_utils import apply_search_filter, apply_sort
from app.services.attachment_service import (
    ENTITY_PETTY_CASH,
    count_attachments_batch,
    delete_all_for_entity,
    list_attachments,
    serialize_attachment,
)
from app.services.petty_cash_list_scope import (
    apply_petty_cash_list_scope,
    list_petty_cash_available_scopes,
    user_can_access_petty_cash_extended,
)
from app.services.payment_request_list_scope import assert_scope_allowed
from app.services.workflow_cleanup import (
    cancel_workflows_for_refs,
    ensure_request_deletable,
)
from app.services.workflow_definition_service import assert_workflow_assignees_ready
from app.services.workflow_start import start_workflow_instance
from app.services.workflow_step_access import user_can_act_on_workflow_step


def _count_expense_lines_batch(db: Session, request_ids: list[int]) -> dict[int, int]:
    if not request_ids:
        return {}
    rows = (
        db.query(PettyCashExpenseLine.petty_cash_request_id, func.count(PettyCashExpenseLine.id))
        .filter(PettyCashExpenseLine.petty_cash_request_id.in_(request_ids))
        .group_by(PettyCashExpenseLine.petty_cash_request_id)
        .all()
    )
    return {int(rid): int(cnt) for rid, cnt in rows}


def workflow_instance_for_petty_cash(
    db: Session, petty_cash_id: int
) -> WorkflowInstance | None:
    """آخرین نمونهٔ فعال تأیید خرج را ترجیح می‌دهد؛ وگرنه درخواست تنخواه."""
    settlement = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
            WorkflowInstance.ref_id == petty_cash_id,
            WorkflowInstance.status.in_(("in_progress", "pending", "returned")),
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )
    if settlement:
        return settlement
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type.in_(
                ("petty_cash", WORKFLOW_REF_PETTY_CASH_SETTLEMENT)
            ),
            WorkflowInstance.ref_id == petty_cash_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def _workflow_instances_for_petty_cash(
    db: Session, petty_cash_id: int
) -> list[WorkflowInstance]:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type.in_(
                ("petty_cash", WORKFLOW_REF_PETTY_CASH_SETTLEMENT)
            ),
            WorkflowInstance.ref_id == petty_cash_id,
        )
        .all()
    )


def _blocking_request(db: Session, requester_id: int) -> PettyCashRequest | None:
    return (
        db.query(PettyCashRequest)
        .filter(
            PettyCashRequest.requester_id == requester_id,
            PettyCashRequest.status.in_([STATUS_PENDING, STATUS_APPROVED]),
            PettyCashRequest.settlement_status != SETTLEMENT_SETTLED,
        )
        .order_by(PettyCashRequest.id.desc())
        .first()
    )


def check_eligibility(db: Session, requester_id: int) -> dict:
    blocker = _blocking_request(db, requester_id)
    if not blocker:
        return {
            "can_create": True,
            "blocking_request_id": None,
            "message": None,
        }
    if blocker.status == STATUS_PENDING:
        msg = (
            f"درخواست تنخواه شماره {blocker.id} هنوز در گردش تأیید است؛ "
            "تا پایان آن نمی‌توانید درخواست جدید ثبت کنید."
        )
    elif blocker.settlement_status == SETTLEMENT_PENDING_APPROVAL:
        msg = (
            f"خرج تنخواه شماره {blocker.id} در حال تأیید مدیر / مدیر مالی / مدیرعامل است؛ "
            "تا پایان آن نمی‌توانید درخواست جدید ثبت کنید."
        )
    else:
        msg = (
            f"تنخواه شماره {blocker.id} پرداخت شده اما جزئیات خرج ثبت نشده؛ "
            "ابتدا اقلام هزینه را وارد یا فایل اکسل را بارگذاری کنید."
        )
    return {
        "can_create": False,
        "blocking_request_id": blocker.id,
        "message": msg,
    }


def _serialize(
    db: Session,
    row: PettyCashRequest,
    *,
    include_lines: bool = True,
    include_attachments: bool = True,
    attachment_count_override: int | None = None,
) -> dict:
    inst = workflow_instance_for_petty_cash(db, row.id)
    lines = []
    if include_lines:
        expense_rows = (
            db.query(PettyCashExpenseLine)
            .filter_by(petty_cash_request_id=row.id)
            .order_by(PettyCashExpenseLine.row_order, PettyCashExpenseLine.id)
            .all()
        )
        lines = [
            {
                "id": ln.id,
                "description": ln.description,
                "amount": float(ln.amount),
                "expense_date": ln.expense_date,
                "source": ln.source,
                "row_order": ln.row_order,
            }
            for ln in expense_rows
        ]
    requester_name = None
    if row.requester_id:
        req = db.get(User, row.requester_id)
        if req:
            parts = [req.first_name, req.last_name]
            requester_name = (
                " ".join(p.strip() for p in parts if p and p.strip()) or req.username
            )

    base = {
        "id": row.id,
        "title": row.title,
        "requester_id": row.requester_id,
        "requester_name": requester_name,
        "amount": float(row.amount),
        "reason": row.reason,
        "requested_date": row.requested_date,
        "status": row.status,
        "settlement_status": row.settlement_status,
        "payer_company_account_id": row.payer_company_account_id,
        "total_expenses": float(row.total_expenses) if row.total_expenses is not None else None,
        "settled_at": row.settled_at,
        "sepidar_registered_at": row.sepidar_registered_at,
        "sepidar_registered_by": row.sepidar_registered_by,
        "sepidar_confirmed_at": row.sepidar_confirmed_at,
        "sepidar_confirmed_by": row.sepidar_confirmed_by,
        "workflow_instance_id": inst.id if inst else None,
        "expense_lines": lines,
        "created_at": row.created_at,
    }
    if include_attachments:
        atts = list_attachments(db, ENTITY_PETTY_CASH, row.id)
        base["attachments"] = [serialize_attachment(a) for a in atts]
        base["attachment_count"] = len(atts)
    else:
        base["attachments"] = []
        base["attachment_count"] = (
            attachment_count_override if attachment_count_override is not None else 0
        )
    return base


def create_petty_cash_request(
    db: Session,
    requester_id: int,
    *,
    amount: float,
    reason: str | None,
    requested_date: date | None,
    title: str | None = None,
    assignees_by_order: dict[str, int] | None = None,
) -> dict:
    from app.services.request_title import resolve_request_title, user_display_name
    from app.services.workflow_messages import REF_TYPE_LABELS

    eligibility = check_eligibility(db, requester_id)
    if not eligibility["can_create"]:
        raise ValueError(eligibility["message"] or "امکان ثبت تنخواه جدید وجود ندارد")

    assert_workflow_assignees_ready(
        db, "petty_cash", submitter_id=requester_id
    )

    requester = db.get(User, requester_id)
    resolved_title = resolve_request_title(
        title=title,
        type_label=REF_TYPE_LABELS.get("petty_cash", "تنخواه"),
        requester_name=user_display_name(requester),
    )

    row = PettyCashRequest(
        requester_id=requester_id,
        title=resolved_title,
        amount=amount,
        reason=(reason or "").strip() or None,
        requested_date=requested_date,
        status=STATUS_PENDING,
        settlement_status=SETTLEMENT_NONE,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    wf_payload: dict = {
        "ref_type": "petty_cash",
        "ref_id": row.id,
        "submitter_id": requester_id,
    }
    if assignees_by_order:
        wf_payload["assignees_by_order"] = assignees_by_order

    try:
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        db.rollback()
        raise
    publish_event("workflow.start", wf_payload)

    return _serialize(db, row, include_lines=False)


def on_workflow_approved(db: Session, petty_cash_id: int) -> None:
    row = db.get(PettyCashRequest, petty_cash_id)
    if not row:
        return
    row.status = STATUS_APPROVED
    row.settlement_status = SETTLEMENT_PENDING
    db.commit()


def on_workflow_rejected(db: Session, petty_cash_id: int) -> None:
    row = db.get(PettyCashRequest, petty_cash_id)
    if not row:
        return
    row.status = STATUS_REJECTED
    db.commit()


def on_settlement_workflow_approved(db: Session, petty_cash_id: int) -> None:
    row = db.get(PettyCashRequest, petty_cash_id)
    if not row:
        return
    row.settlement_status = SETTLEMENT_SETTLED
    row.settled_at = datetime.utcnow()
    db.commit()


def on_settlement_workflow_rejected(db: Session, petty_cash_id: int) -> None:
    """رد کامل تأیید خرج → برگشت به امکان اصلاح و ارسال مجدد خرج."""
    row = db.get(PettyCashRequest, petty_cash_id)
    if not row:
        return
    row.settlement_status = SETTLEMENT_PENDING
    row.settled_at = None
    db.commit()


def _get_owned_request(db: Session, request_id: int, user_id: int) -> PettyCashRequest:
    row = db.get(PettyCashRequest, request_id)
    if not row:
        raise ValueError("درخواست تنخواه یافت نشد")
    if row.requester_id != user_id:
        raise ValueError("access denied")
    return row


def _save_expense_lines(
    db: Session,
    row: PettyCashRequest,
    lines: list[PettyCashExpenseLineIn],
    *,
    source: str,
    replace_existing: bool,
) -> None:
    if row.status != STATUS_APPROVED:
        raise ValueError("فقط پس از تأیید و پرداخت تنخواه می‌توان جزئیات خرج را ثبت کرد")
    if row.settlement_status == SETTLEMENT_SETTLED:
        raise ValueError("این تنخواه قبلاً تسویه شده و قابل ویرایش نیست")
    if row.settlement_status == SETTLEMENT_PENDING_APPROVAL:
        raise ValueError("خرج این تنخواه در حال تأیید است و فعلاً قابل ویرایش نیست")

    if replace_existing:
        db.query(PettyCashExpenseLine).filter_by(
            petty_cash_request_id=row.id
        ).delete(synchronize_session=False)

    total = 0.0
    for idx, line in enumerate(lines):
        db.add(
            PettyCashExpenseLine(
                petty_cash_request_id=row.id,
                description=line.description.strip(),
                amount=line.amount,
                expense_date=line.expense_date,
                source=source,
                row_order=idx + 1,
            )
        )
        total += line.amount

    if total > float(row.amount) * 1.0001:
        raise ValueError(
            f"جمع اقلام ({total:,.0f}) از مبلغ تنخواه ({float(row.amount):,.0f}) بیشتر است"
        )

    row.total_expenses = total
    row.settlement_status = SETTLEMENT_PENDING_APPROVAL
    row.settled_at = None
    db.commit()
    db.refresh(row)

    assert_workflow_assignees_ready(
        db,
        WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
        submitter_id=row.requester_id,
    )
    wf_payload = {
        "ref_type": WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
        "ref_id": row.id,
        "submitter_id": row.requester_id,
        "requester_id": row.requester_id,
    }
    try:
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        row.settlement_status = SETTLEMENT_PENDING
        db.commit()
        raise
    publish_event("workflow.start", wf_payload)
    db.refresh(row)


def submit_expenses_manual(
    db: Session,
    request_id: int,
    user_id: int,
    lines: list[PettyCashExpenseLineIn],
    *,
    replace_existing: bool = True,
) -> dict:
    row = _get_owned_request(db, request_id, user_id)
    _save_expense_lines(db, row, lines, source=EXPENSE_SOURCE_MANUAL, replace_existing=replace_existing)
    return _serialize(db, row)


def submit_expenses_excel(
    db: Session,
    request_id: int,
    user_id: int,
    file_bytes: bytes,
    *,
    replace_existing: bool = True,
) -> dict:
    row = _get_owned_request(db, request_id, user_id)
    lines = parse_expense_excel(file_bytes)
    _save_expense_lines(db, row, lines, source=EXPENSE_SOURCE_EXCEL, replace_existing=replace_existing)
    return _serialize(db, row)


def get_petty_cash(db: Session, request_id: int, user) -> dict:
    row = db.get(PettyCashRequest, request_id)
    if not row:
        raise ValueError("درخواست تنخواه یافت نشد")
    if not user_can_access_petty_cash_extended(db, user, row):
        from app.models.workflow_step import WorkflowStep

        instances = _workflow_instances_for_petty_cash(db, request_id)
        if not instances:
            raise ValueError("access denied")
        allowed = False
        for inst in instances:
            steps = db.query(WorkflowStep).filter_by(instance_id=inst.id).all()
            if any(user_can_act_on_workflow_step(user, st) for st in steps):
                allowed = True
                break
        if not allowed:
            raise ValueError("access denied")
    return _serialize(db, row)


def get_petty_cash_by_workflow_instance(
    db: Session, instance_id: int, user
) -> dict:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type not in ("petty_cash", WORKFLOW_REF_PETTY_CASH_SETTLEMENT):
        raise ValueError("درخواست تنخواه برای این نمونه workflow یافت نشد")
    return get_petty_cash(db, inst.ref_id, user)


def get_petty_cash_list_capabilities(db: Session, viewer: User) -> dict:
    return {"scopes": list_petty_cash_available_scopes(db, viewer)}


def list_petty_cash_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    search: str | None = None,
) -> list[dict]:
    resolved_scope = assert_scope_allowed(db, viewer, scope)
    query = db.query(PettyCashRequest)
    query = apply_petty_cash_list_scope(db, query, user=viewer, scope=resolved_scope)
    query = apply_search_filter(
        query, PettyCashRequest, search, ["reason", "status", "settlement_status"]
    )
    query = apply_sort(query, PettyCashRequest, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    ids = [r.id for r in rows]
    att_counts = count_attachments_batch(db, ENTITY_PETTY_CASH, ids)
    line_counts = _count_expense_lines_batch(db, ids)
    out: list[dict] = []
    for r in rows:
        item = _serialize(
            db,
            r,
            include_lines=False,
            include_attachments=False,
            attachment_count_override=att_counts.get(r.id, 0),
        )
        item["expense_line_count"] = line_counts.get(r.id, 0)
        out.append(item)
    return out


def count_petty_cash_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    search: str | None = None,
) -> int:
    resolved_scope = assert_scope_allowed(db, viewer, scope)
    query = db.query(func.count(PettyCashRequest.id))
    query = apply_petty_cash_list_scope(db, query, user=viewer, scope=resolved_scope)
    query = apply_search_filter(
        query, PettyCashRequest, search, ["reason", "status", "settlement_status"]
    )
    return query.scalar() or 0


def delete_petty_cash_request(db: Session, request_id: int, user_id: int) -> None:
    row = _get_owned_request(db, request_id, user_id)
    if row.status != STATUS_PENDING:
        raise ValueError("فقط درخواست در انتظار تأیید قابل حذف است")
    refs = ("petty_cash", WORKFLOW_REF_PETTY_CASH_SETTLEMENT)
    ensure_request_deletable(db, ref_types=refs, ref_id=request_id)
    cancel_workflows_for_refs(db, refs, request_id)
    delete_all_for_entity(db, ENTITY_PETTY_CASH, request_id)
    db.query(PettyCashExpenseLine).filter_by(petty_cash_request_id=request_id).delete(
        synchronize_session=False
    )
    db.delete(row)
    db.commit()
