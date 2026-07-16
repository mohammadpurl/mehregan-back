from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.financial_document import (
    DOCUMENT_TYPES,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    WORKFLOW_REF_FINANCIAL_DOCUMENT,
)
from app.infrastructure.messaging.publisher import publish_event
from app.models.financial_document import FinancialDocument
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.attachment_service import (
    ENTITY_FINANCIAL_DOCUMENT,
    count_attachments_batch,
    delete_all_for_entity,
    list_attachments,
    serialize_attachment,
)
from app.services.financial_document_list_scope import (
    REF_TYPE,
    apply_financial_document_list_scope,
    list_financial_document_scopes,
    user_can_access_financial_document_extended,
)
from app.services.payment_request_list_scope import assert_scope_allowed
from app.services.procurement.invoice_service import user_is_finance_manager
from app.services.query_utils import apply_search_filter, apply_sort
from app.services.workflow_cleanup import cancel_workflow_for_ref
from app.services.workflow_definition_service import assert_workflow_assignees_ready
from app.services.workflow_start import start_workflow_instance
from app.services.workflow_step_access import user_can_act_on_workflow_step


def _assert_finance_submitter(user: User) -> None:
    if not user_is_finance_manager(user):
        raise ValueError("ثبت سند مالی فقط توسط واحد مالی مجاز است")


def workflow_instance_for_document(
    db: Session, document_id: int
) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == REF_TYPE,
            WorkflowInstance.ref_id == document_id,
        )
        .first()
    )


def _serialize(
    db: Session,
    row: FinancialDocument,
    *,
    include_attachments: bool = True,
    attachment_count_override: int | None = None,
) -> dict:
    inst = workflow_instance_for_document(db, row.id)
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
        "requester_id": row.requester_id,
        "requester_name": requester_name,
        "document_type": row.document_type,
        "title": row.title,
        "description": row.description,
        "amount": float(row.amount) if row.amount is not None else None,
        "document_date": row.document_date,
        "check_number": row.check_number,
        "party_name": row.party_name,
        "status": row.status,
        "finance_confirmed_at": row.finance_confirmed_at,
        "sepidar_registered_at": row.sepidar_registered_at,
        "sepidar_registered_by": row.sepidar_registered_by,
        "sepidar_confirmed_at": row.sepidar_confirmed_at,
        "sepidar_confirmed_by": row.sepidar_confirmed_by,
        "workflow_instance_id": inst.id if inst else None,
        "created_at": row.created_at,
    }
    if include_attachments:
        atts = list_attachments(db, ENTITY_FINANCIAL_DOCUMENT, row.id)
        base["attachments"] = [serialize_attachment(a) for a in atts]
        base["attachment_count"] = len(atts)
    else:
        base["attachments"] = []
        base["attachment_count"] = (
            attachment_count_override if attachment_count_override is not None else 0
        )
    return base


def create_financial_document(
    db: Session,
    requester: User,
    *,
    document_type: str,
    title: str | None,
    description: str | None,
    amount: float | None,
    document_date: date | None,
    check_number: str | None,
    party_name: str | None,
    assignees_by_order: dict[str, int] | None = None,
) -> dict:
    _assert_finance_submitter(requester)

    doc_type = (document_type or "check").strip().lower()
    if doc_type not in DOCUMENT_TYPES:
        raise ValueError("نوع سند نامعتبر است")

    assert_workflow_assignees_ready(
        db, WORKFLOW_REF_FINANCIAL_DOCUMENT, submitter_id=requester.id
    )

    row = FinancialDocument(
        requester_id=requester.id,
        document_type=doc_type,
        title=(title or "").strip() or None,
        description=(description or "").strip() or None,
        amount=amount,
        document_date=document_date,
        check_number=(check_number or "").strip() or None,
        party_name=(party_name or "").strip() or None,
        status=STATUS_PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    wf_payload: dict = {
        "ref_type": WORKFLOW_REF_FINANCIAL_DOCUMENT,
        "ref_id": row.id,
        "submitter_id": requester.id,
    }
    if assignees_by_order:
        wf_payload["assignees_by_order"] = assignees_by_order

    try:
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        db.rollback()
        raise
    publish_event("workflow.start", wf_payload)

    return _serialize(db, row, include_attachments=False)


def on_workflow_approved(db: Session, document_id: int) -> None:
    row = db.get(FinancialDocument, document_id)
    if not row:
        return
    row.status = STATUS_APPROVED
    row.finance_confirmed_at = datetime.utcnow()
    db.commit()


def on_workflow_rejected(db: Session, document_id: int) -> None:
    row = db.get(FinancialDocument, document_id)
    if not row:
        return
    row.status = STATUS_REJECTED
    db.commit()


def get_financial_document(db: Session, document_id: int, user: User) -> dict:
    row = db.get(FinancialDocument, document_id)
    if not row:
        raise ValueError("سند مالی یافت نشد")
    if not user_can_access_financial_document(db, user, row):
        raise ValueError("access denied")
    return _serialize(db, row)


def get_financial_document_by_workflow_instance(
    db: Session, instance_id: int, user: User
) -> dict:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type != REF_TYPE:
        raise ValueError("این نمونه workflow مربوط به سند مالی نیست")
    return get_financial_document(db, int(inst.ref_id), user)


def user_can_access_financial_document(
    db: Session, user: User, row: FinancialDocument
) -> bool:
    if user_can_access_financial_document_extended(db, user, row):
        return True
    inst = workflow_instance_for_document(db, row.id)
    if not inst:
        return False
    user_role_ids = {r.id for r in user.get_roles()}
    steps = db.query(WorkflowStep).filter(WorkflowStep.instance_id == inst.id).all()
    for st in steps:
        if st.assigned_user_id == user.id:
            return True
        if st.role_id in user_role_ids:
            return True
    return False


def list_financial_documents(
    db: Session,
    *,
    viewer: User,
    scope: str | None,
    offset: int,
    limit: int,
    sort_by: str,
    sort_order: str,
    search: str | None,
) -> list[dict]:
    resolved = assert_scope_allowed(db, viewer, scope)
    q = db.query(FinancialDocument)
    q = apply_financial_document_list_scope(db, q, user=viewer, scope=resolved)
    q = apply_search_filter(
        q,
        FinancialDocument,
        search,
        ["title", "description", "check_number", "party_name"],
    )
    q = apply_sort(q, FinancialDocument, sort_by, sort_order)
    rows = q.offset(offset).limit(limit).all()
    ids = [r.id for r in rows]
    counts = count_attachments_batch(db, ENTITY_FINANCIAL_DOCUMENT, ids)
    return [
        _serialize(db, r, include_attachments=False, attachment_count_override=counts.get(r.id, 0))
        for r in rows
    ]


def count_financial_documents(
    db: Session, *, viewer: User, scope: str | None, search: str | None
) -> int:
    resolved = assert_scope_allowed(db, viewer, scope)
    q = db.query(func.count(FinancialDocument.id))
    q = apply_financial_document_list_scope(db, q, user=viewer, scope=resolved)
    q = apply_search_filter(
        q,
        FinancialDocument,
        search,
        ["title", "description", "check_number", "party_name"],
    )
    return int(q.scalar() or 0)


def get_list_capabilities(db: Session, viewer: User) -> dict:
    return {"scopes": list_financial_document_scopes(db, viewer)}


def delete_financial_document(db: Session, document_id: int, user: User) -> None:
    row = db.get(FinancialDocument, document_id)
    if not row:
        raise ValueError("سند مالی یافت نشد")
    if row.requester_id != user.id:
        raise ValueError("فقط ثبت‌کننده می‌تواند حذف کند")
    if row.status != STATUS_PENDING:
        raise ValueError("فقط سندهای در انتظار تأیید قابل حذف هستند")
    inst = workflow_instance_for_document(db, document_id)
    if inst and inst.status not in ("pending", "in_progress", "active"):
        raise ValueError("گردش‌کار این سند دیگر قابل حذف نیست")
    cancel_workflow_for_ref(db, REF_TYPE, document_id)
    delete_all_for_entity(db, ENTITY_FINANCIAL_DOCUMENT, document_id)
    db.delete(row)
    db.commit()
