"""محدودهٔ نمایش لیست درخواست‌های مالی بر اساس نقش و سلسله‌مراتب سازمانی."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, Query

from app.models.department import Department
from app.models.payment_request import PaymentRequest
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.permission import user_has_permission_db

SCOPE_MINE = "mine"
SCOPE_TEAM = "team"
SCOPE_ALL = "all"
SCOPE_APPROVER = "approver"
SCOPE_PARTICIPATED = "participated"

ALL_SCOPES = frozenset(
    {SCOPE_MINE, SCOPE_TEAM, SCOPE_ALL, SCOPE_APPROVER, SCOPE_PARTICIPATED}
)

_GLOBAL_VIEW_ROLE_NAMES = frozenset(
    {
        "finance_manager",
        "accountant",
        "ceo",
        "managing_director",
        "admin",
        "super-admin",
        "system_admin",
    }
)

_MANAGER_ROLE_NAMES = frozenset(
    {
        "manager",
        "project_manager",
    }
)


def _user_role_names(user: User) -> set[str]:
    return {r.name.strip().lower() for r in user.get_roles() if r and r.name}


def user_can_view_all_payment_requests(db: Session, user: User) -> bool:
    if user_has_permission_db(db, user.id, "workflow.all.read"):
        return True
    if user_has_permission_db(db, user.id, "admin.manage"):
        return True
    names = _user_role_names(user)
    return bool(names & _GLOBAL_VIEW_ROLE_NAMES)


def user_can_view_team_payment_requests(db: Session, user: User) -> bool:
    if user_can_view_all_payment_requests(db, user):
        return True
    if collect_team_member_user_ids(db, user.id):
        return True
    names = _user_role_names(user)
    if names & _MANAGER_ROLE_NAMES:
        return True
    return _is_department_head(db, user.id)


def _is_department_head(db: Session, user_id: int) -> bool:
    return (
        db.query(Department.id)
        .filter(Department.head_user_id == user_id)
        .first()
        is not None
    )


def _department_subtree_ids(db: Session, root_id: int) -> set[int]:
    rows = db.query(Department.id, Department.parent_id).all()
    children: dict[int | None, list[int]] = defaultdict(list)
    for did, pid in rows:
        children[pid].append(did)
    out: set[int] = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def _collect_manager_descendants(db: Session, manager_id: int) -> set[int]:
    rows = db.query(User.id, User.manager_id).filter(User.is_active == True).all()  # noqa: E712
    by_manager: dict[int | None, list[int]] = defaultdict(list)
    for uid, mid in rows:
        by_manager[mid].append(uid)
    out: set[int] = set()
    stack = list(by_manager.get(manager_id, []))
    while stack:
        uid = stack.pop()
        if uid in out or uid == manager_id:
            continue
        out.add(uid)
        stack.extend(by_manager.get(uid, []))
    return out


def collect_team_member_user_ids(db: Session, viewer_id: int) -> set[int]:
    """کاربران زیرمجموعه (گزارش مستقیم/غیرمستقیم + اعضای واحدهای تحت مدیریت)."""
    member_ids: set[int] = _collect_manager_descendants(db, viewer_id)

    headed = (
        db.query(Department.id)
        .filter(Department.head_user_id == viewer_id)
        .all()
    )
    dept_ids: set[int] = set()
    for (did,) in headed:
        dept_ids |= _department_subtree_ids(db, did)

    if dept_ids:
        rows = (
            db.query(User.id)
            .filter(User.department_id.in_(dept_ids), User.id != viewer_id)
            .all()
        )
        member_ids |= {r[0] for r in rows}

    member_ids.discard(viewer_id)
    return member_ids


def list_available_scopes(db: Session, user: User) -> list[str]:
    scopes = [SCOPE_MINE, SCOPE_APPROVER, SCOPE_PARTICIPATED]
    if user_can_view_team_payment_requests(db, user):
        scopes.insert(1, SCOPE_TEAM)
    if user_can_view_all_payment_requests(db, user):
        scopes.append(SCOPE_ALL)
    return scopes


def assert_scope_allowed(db: Session, user: User, scope: str | None) -> str:
    normalized = (scope or SCOPE_MINE).strip().lower()
    if normalized not in ALL_SCOPES:
        raise ValueError(f"محدوده نامعتبر: {scope}")
    if normalized == SCOPE_ALL and not user_can_view_all_payment_requests(db, user):
        raise ValueError("دسترسی به همه درخواست‌های مالی مجاز نیست")
    if normalized == SCOPE_TEAM and not user_can_view_team_payment_requests(db, user):
        raise ValueError("دسترسی به درخواست‌های واحد مجاز نیست")
    return normalized


def apply_payment_request_list_scope(
    db: Session,
    query: Query,
    *,
    user: User,
    scope: str,
) -> Query:
    scope = assert_scope_allowed(db, user, scope)

    if scope == SCOPE_MINE:
        return query.filter(PaymentRequest.requester_id == user.id)

    if scope == SCOPE_TEAM:
        team_ids = collect_team_member_user_ids(db, user.id)
        if not team_ids:
            return query.filter(PaymentRequest.id < 0)
        return query.filter(PaymentRequest.requester_id.in_(team_ids))

    if scope == SCOPE_ALL:
        return query

    if scope == SCOPE_APPROVER:
        return query.filter(
            exists(
                select(1)
                .select_from(WorkflowInstance)
                .join(WorkflowStep, WorkflowStep.instance_id == WorkflowInstance.id)
                .where(
                    WorkflowInstance.ref_type == "payment_request",
                    WorkflowInstance.ref_id == PaymentRequest.id,
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
                    WorkflowInstance.ref_type == "payment_request",
                    WorkflowInstance.ref_id == PaymentRequest.id,
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

    return query.filter(PaymentRequest.requester_id == user.id)


def user_can_access_payment_request_extended(
    db: Session, user: User, pr: PaymentRequest
) -> bool:
    if pr.requester_id == user.id:
        return True
    if user_can_view_all_payment_requests(db, user):
        return True
    if pr.requester_id in collect_team_member_user_ids(db, user.id):
        return True
    return False
