"""محدودهٔ نمایش لیست درخواست‌های خرید بر اساس نقش و گردش‌کار."""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Query, Session

from app.constants.procurement import PURCHASE_WORKFLOW_REFS, REQUEST_TYPE_PURCHASE
from app.models.request import Request
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.payment_request_list_scope import (
    SCOPE_ALL,
    SCOPE_APPROVER,
    SCOPE_MINE,
    SCOPE_PARTICIPATED,
    user_can_view_all_payment_requests,
)

SCOPE_ALL_SCOPES = frozenset({SCOPE_MINE, SCOPE_ALL, SCOPE_APPROVER, SCOPE_PARTICIPATED})

_PURCHASE_WORKFLOW_REFS = PURCHASE_WORKFLOW_REFS


def user_can_view_all_purchase_requests(db: Session, user: User) -> bool:
    return user_can_view_all_payment_requests(db, user)


def list_available_purchase_scopes(db: Session, user: User) -> list[str]:
    scopes = [SCOPE_MINE, SCOPE_APPROVER, SCOPE_PARTICIPATED]
    if user_can_view_all_purchase_requests(db, user):
        scopes.append(SCOPE_ALL)
    return scopes


def assert_purchase_scope_allowed(db: Session, user: User, scope: str | None) -> str:
    normalized = (scope or SCOPE_MINE).strip().lower()
    if normalized not in SCOPE_ALL_SCOPES:
        raise ValueError(f"محدوده نامعتبر: {scope}")
    if normalized == SCOPE_ALL and not user_can_view_all_purchase_requests(db, user):
        raise ValueError("دسترسی به همه درخواست‌های خرید مجاز نیست")
    return normalized


def apply_purchase_request_list_scope(
    db: Session,
    query: Query,
    *,
    user: User,
    scope: str,
) -> Query:
    scope = assert_purchase_scope_allowed(db, user, scope)

    if scope == SCOPE_MINE:
        return query.filter(Request.requester_id == user.id)

    if scope == SCOPE_ALL:
        return query

    if scope == SCOPE_APPROVER:
        return query.filter(
            exists(
                select(1)
                .select_from(WorkflowInstance)
                .join(WorkflowStep, WorkflowStep.instance_id == WorkflowInstance.id)
                .where(
                    WorkflowInstance.ref_type.in_(_PURCHASE_WORKFLOW_REFS),
                    WorkflowInstance.ref_id == Request.id,
                    WorkflowStep.status == "pending",
                    WorkflowStep.assigned_user_id == user.id,
                )
            )
        )

    if scope == SCOPE_PARTICIPATED:
        return query.filter(
            exists(
                select(1)
                .select_from(WorkflowInstance)
                .join(WorkflowStep, WorkflowStep.instance_id == WorkflowInstance.id)
                .where(
                    WorkflowInstance.ref_type.in_(_PURCHASE_WORKFLOW_REFS),
                    WorkflowInstance.ref_id == Request.id,
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

    return query.filter(Request.requester_id == user.id)


def get_purchase_request_list_capabilities(db: Session, viewer: User) -> dict:
    return {"scopes": list_available_purchase_scopes(db, viewer)}


def user_can_access_purchase_request(db: Session, user: User, request_id: int) -> bool:
    """دسترسی به یک درخواست خرید (مثلاً برای دانلود پیوست پیش‌فاکتور)."""
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        return False
    if req.requester_id == user.id:
        return True
    if user_can_view_all_purchase_requests(db, user):
        return True

    user_role_ids = {r.id for r in user.get_roles()}
    pending_conditions = [
        and_(
            WorkflowStep.status == "pending",
            WorkflowStep.assigned_user_id == user.id,
        ),
    ]
    if user_role_ids:
        pending_conditions.append(
            and_(
                WorkflowStep.status == "pending",
                WorkflowStep.role_id.in_(user_role_ids),
            )
        )
    pending_match = or_(*pending_conditions)

    return (
        db.query(
            exists(
                select(1)
                .select_from(WorkflowInstance)
                .join(WorkflowStep, WorkflowStep.instance_id == WorkflowInstance.id)
                .where(
                    WorkflowInstance.ref_type.in_(_PURCHASE_WORKFLOW_REFS),
                    WorkflowInstance.ref_id == request_id,
                    or_(
                        pending_match,
                        WorkflowStep.approved_by == user.id,
                        and_(
                            WorkflowStep.assigned_user_id == user.id,
                            WorkflowStep.status.in_(("approved", "rejected", "cancelled")),
                        ),
                    ),
                )
            )
        ).scalar()
        is True
    )
