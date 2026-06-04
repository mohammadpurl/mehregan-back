"""محدودهٔ نمایش لیست تنخواه — همان الگوی درخواست پرداخت."""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Query, Session

from app.models.petty_cash_request import PettyCashRequest
from app.models.user import User
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
    user_can_view_all_payment_requests,
    user_can_view_team_payment_requests,
)

REF_TYPE = "petty_cash"


def list_petty_cash_available_scopes(db: Session, user: User) -> list[str]:
    return list_available_scopes(db, user)


def user_can_access_petty_cash_extended(
    db: Session, user: User, row: PettyCashRequest
) -> bool:
    if row.requester_id == user.id:
        return True
    if user_can_view_all_payment_requests(db, user):
        return True
    if row.requester_id in collect_team_member_user_ids(db, user.id):
        return True
    return False


def apply_petty_cash_list_scope(
    db: Session,
    query: Query,
    *,
    user: User,
    scope: str,
) -> Query:
    scope = assert_scope_allowed(db, user, scope)

    if scope == SCOPE_MINE:
        return query.filter(PettyCashRequest.requester_id == user.id)

    if scope == SCOPE_TEAM:
        team_ids = collect_team_member_user_ids(db, user.id)
        if not team_ids:
            return query.filter(PettyCashRequest.id < 0)
        return query.filter(PettyCashRequest.requester_id.in_(team_ids))

    if scope == SCOPE_ALL:
        return query

    if scope == SCOPE_APPROVER:
        return query.filter(
            exists(
                select(1)
                .select_from(WorkflowInstance)
                .join(WorkflowStep, WorkflowStep.instance_id == WorkflowInstance.id)
                .where(
                    WorkflowInstance.ref_type == REF_TYPE,
                    WorkflowInstance.ref_id == PettyCashRequest.id,
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
                    WorkflowInstance.ref_type == REF_TYPE,
                    WorkflowInstance.ref_id == PettyCashRequest.id,
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

    return query.filter(PettyCashRequest.requester_id == user.id)
