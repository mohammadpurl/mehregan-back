"""لیست نمونه‌های گردش‌کار برای پیگیری سازمانی."""

from __future__ import annotations

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.financial_document import FinancialDocument
from app.models.mission_request import MissionRequest
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.request import Request
from app.models.user import User
from app.models.warehouse_form import WarehouseForm
from app.models.workflow_form import WorkflowForm
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.payment_request_list_scope import (
    ALL_SCOPES,
    SCOPE_ALL,
    SCOPE_APPROVER,
    SCOPE_MINE,
    SCOPE_PARTICIPATED,
    SCOPE_TEAM,
    assert_scope_allowed,
    collect_team_member_user_ids,
    list_available_scopes,
)
from app.services.query_utils import apply_search_filter, apply_sort
from app.services.workflow_messages import ref_type_label


def list_workflow_instance_scopes(db: Session, user: User) -> list[str]:
    return list_available_scopes(db, user)


def _requester_subquery_for_ref(user_id: int):
    """فیلتر instanceهایی که درخواست‌کنندهٔ مرجع آن‌ها user_id است."""
    return or_(
        and_(
            WorkflowInstance.ref_type == "payment_request",
            exists(
                select(1)
                .select_from(PaymentRequest)
                .where(
                    PaymentRequest.id == WorkflowInstance.ref_id,
                    PaymentRequest.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "payment_order",
            exists(
                select(1)
                .select_from(PaymentRequest)
                .where(
                    PaymentRequest.id == WorkflowInstance.ref_id,
                    PaymentRequest.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "financial_document",
            exists(
                select(1)
                .select_from(FinancialDocument)
                .where(
                    FinancialDocument.id == WorkflowInstance.ref_id,
                    FinancialDocument.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "petty_cash",
            exists(
                select(1)
                .select_from(PettyCashRequest)
                .where(
                    PettyCashRequest.id == WorkflowInstance.ref_id,
                    PettyCashRequest.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type.in_(
                ("request", "procurement", "product_request", "purchase_request")
            ),
            exists(
                select(1)
                .select_from(Request)
                .where(
                    Request.id == WorkflowInstance.ref_id,
                    Request.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "financial_document",
            exists(
                select(1)
                .select_from(FinancialDocument)
                .where(
                    FinancialDocument.id == WorkflowInstance.ref_id,
                    FinancialDocument.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "mission_request",
            exists(
                select(1)
                .select_from(MissionRequest)
                .where(
                    MissionRequest.id == WorkflowInstance.ref_id,
                    MissionRequest.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "workflow_form",
            exists(
                select(1)
                .select_from(WorkflowForm)
                .where(
                    WorkflowForm.id == WorkflowInstance.ref_id,
                    WorkflowForm.requester_id == user_id,
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "warehouse_form",
            exists(
                select(1)
                .select_from(WarehouseForm)
                .where(
                    WarehouseForm.id == WorkflowInstance.ref_id,
                    WarehouseForm.requester_id == user_id,
                )
            ),
        ),
    )


def _team_requester_filter(team_ids: set[int]):
    if not team_ids:
        return WorkflowInstance.id < 0
    return or_(
        and_(
            WorkflowInstance.ref_type == "payment_request",
            exists(
                select(1)
                .select_from(PaymentRequest)
                .where(
                    PaymentRequest.id == WorkflowInstance.ref_id,
                    PaymentRequest.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "payment_order",
            exists(
                select(1)
                .select_from(PaymentRequest)
                .where(
                    PaymentRequest.id == WorkflowInstance.ref_id,
                    PaymentRequest.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "financial_document",
            exists(
                select(1)
                .select_from(FinancialDocument)
                .where(
                    FinancialDocument.id == WorkflowInstance.ref_id,
                    FinancialDocument.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "petty_cash",
            exists(
                select(1)
                .select_from(PettyCashRequest)
                .where(
                    PettyCashRequest.id == WorkflowInstance.ref_id,
                    PettyCashRequest.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type.in_(
                ("request", "procurement", "product_request", "purchase_request")
            ),
            exists(
                select(1)
                .select_from(Request)
                .where(
                    Request.id == WorkflowInstance.ref_id,
                    Request.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "mission_request",
            exists(
                select(1)
                .select_from(MissionRequest)
                .where(
                    MissionRequest.id == WorkflowInstance.ref_id,
                    MissionRequest.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "workflow_form",
            exists(
                select(1)
                .select_from(WorkflowForm)
                .where(
                    WorkflowForm.id == WorkflowInstance.ref_id,
                    WorkflowForm.requester_id.in_(team_ids),
                )
            ),
        ),
        and_(
            WorkflowInstance.ref_type == "warehouse_form",
            exists(
                select(1)
                .select_from(WarehouseForm)
                .where(
                    WarehouseForm.id == WorkflowInstance.ref_id,
                    WarehouseForm.requester_id.in_(team_ids),
                )
            ),
        ),
    )


def apply_workflow_instance_list_scope(db: Session, query, *, user: User, scope: str):
    scope = assert_scope_allowed(db, user, scope)

    if scope == SCOPE_ALL:
        return query

    if scope == SCOPE_MINE:
        return query.filter(
            or_(
                _requester_subquery_for_ref(user.id),
                exists(
                    select(1)
                    .select_from(WorkflowStep)
                    .where(
                        WorkflowStep.instance_id == WorkflowInstance.id,
                        WorkflowStep.assigned_user_id == user.id,
                    )
                ),
            )
        )

    if scope == SCOPE_TEAM:
        team_ids = collect_team_member_user_ids(db, user.id)
        return query.filter(_team_requester_filter(team_ids))

    if scope == SCOPE_APPROVER:
        return query.filter(
            exists(
                select(1)
                .select_from(WorkflowStep)
                .where(
                    WorkflowStep.instance_id == WorkflowInstance.id,
                    WorkflowStep.status == "pending",
                    WorkflowStep.assigned_user_id == user.id,
                )
            )
        )

    if scope == SCOPE_PARTICIPATED:
        return query.filter(
            exists(
                select(1)
                .select_from(WorkflowStep)
                .where(
                    WorkflowStep.instance_id == WorkflowInstance.id,
                    or_(
                        WorkflowStep.approved_by == user.id,
                        and_(
                            WorkflowStep.assigned_user_id == user.id,
                            WorkflowStep.status.in_(("approved", "rejected", "cancelled")),
                        ),
                    ),
                )
            )
        )

    return query.filter(_requester_subquery_for_ref(user.id))


def _user_display(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def _resolve_requester_id(db: Session, inst: WorkflowInstance) -> int | None:
    rt, rid = inst.ref_type, inst.ref_id
    if rt in ("payment_request", "payment_order"):
        row = db.get(PaymentRequest, rid)
        return row.requester_id if row else None
    if rt == "financial_document":
        row = db.get(FinancialDocument, rid)
        return row.requester_id if row else None
    if rt == "mission_request":
        row = db.get(MissionRequest, rid)
        return row.requester_id if row else None
    if rt == "petty_cash":
        row = db.get(PettyCashRequest, rid)
        return row.requester_id if row else None
    if rt in ("request", "procurement", "product_request", "purchase_request"):
        row = db.get(Request, rid)
        return row.requester_id if row else None
    if rt == "workflow_form":
        row = db.get(WorkflowForm, rid)
        return row.requester_id if row else None
    if rt == "warehouse_form":
        row = db.get(WarehouseForm, rid)
        return row.requester_id if row else None
    return None


def serialize_workflow_instance_row(db: Session, inst: WorkflowInstance) -> dict:
    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.instance_id == inst.id)
        .order_by(WorkflowStep.order)
        .all()
    )
    pending = next((s for s in steps if s.status == "pending"), None)
    assignee = (
        db.get(User, pending.assigned_user_id) if pending and pending.assigned_user_id else None
    )
    requester_id = _resolve_requester_id(db, inst)
    requester = db.get(User, requester_id) if requester_id else None
    last_at = None
    for s in reversed(steps):
        if s.approved_at:
            last_at = s.approved_at
            break

    return {
        "id": inst.id,
        "ref_type": inst.ref_type,
        "ref_id": inst.ref_id,
        "ref_label": ref_type_label(inst.ref_type),
        "status": inst.status,
        "requester_id": requester_id,
        "requester_name": _user_display(requester),
        "current_step_order": pending.order if pending else None,
        "current_assignee_id": pending.assigned_user_id if pending else None,
        "current_assignee_name": _user_display(assignee),
        "updated_at": last_at.isoformat() if last_at else None,
        "title": f"{ref_type_label(inst.ref_type)} #{inst.ref_id}",
    }


def list_workflow_instances(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    ref_type: str | None = None,
    status: str | None = None,
    instance_id: int | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    search: str | None = None,
) -> list[dict]:
    resolved = assert_scope_allowed(db, viewer, scope)
    query = db.query(WorkflowInstance)
    query = apply_workflow_instance_list_scope(db, query, user=viewer, scope=resolved)
    if ref_type:
        query = query.filter(WorkflowInstance.ref_type == ref_type.strip())
    if status:
        query = query.filter(WorkflowInstance.status == status.strip())
    if instance_id:
        query = query.filter(WorkflowInstance.id == instance_id)
    query = apply_search_filter(
        query,
        WorkflowInstance,
        search,
        ["ref_type", "status"],
    )
    query = apply_sort(query, WorkflowInstance, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [serialize_workflow_instance_row(db, r) for r in rows]


def count_workflow_instances(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    ref_type: str | None = None,
    status: str | None = None,
    instance_id: int | None = None,
    search: str | None = None,
) -> int:
    resolved = assert_scope_allowed(db, viewer, scope)
    query = db.query(func.count(WorkflowInstance.id))
    query = apply_workflow_instance_list_scope(db, query, user=viewer, scope=resolved)
    if ref_type:
        query = query.filter(WorkflowInstance.ref_type == ref_type.strip())
    if status:
        query = query.filter(WorkflowInstance.status == status.strip())
    if instance_id:
        query = query.filter(WorkflowInstance.id == instance_id)
    query = apply_search_filter(
        query,
        WorkflowInstance,
        search,
        ["ref_type", "status"],
    )
    return query.scalar() or 0


def user_can_view_workflow_instance(db: Session, viewer: User, instance_id: int) -> bool:
    """آیا viewer مجاز به دیدن این instance است (بر اساس scopeهای مجاز)."""
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return False
    for scope in list_available_scopes(db, viewer):
        query = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id)
        query = apply_workflow_instance_list_scope(db, query, user=viewer, scope=scope)
        if query.first():
            return True
    return False


def get_workflow_instance_for_viewer(
    db: Session,
    *,
    viewer: User,
    instance_id: int,
) -> dict | None:
    if not user_can_view_workflow_instance(db, viewer, instance_id):
        return None
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None
    return serialize_workflow_instance_row(db, inst)
