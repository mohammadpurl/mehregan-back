import random
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user import User
from app.models.user_role import UserRole
from app.models.assignment_rule import AssignmentRule
from app.models.inbox import InboxItem


def resolve_assignee_for_role(
    db: Session,
    role_id: int,
    preferred_user_id: int | None,
    *,
    exclude_user_ids: set[int] | None = None,
    trust_preferred_without_role: bool = False,
) -> User | None:
    """
    If preferred_user_id is set and the user exists, assign to that user (explicit
    referral). Otherwise pick someone with role_id using assignment rules.
    """
    if preferred_user_id is not None:
        user = db.get(User, preferred_user_id)
        if user and (not exclude_user_ids or user.id not in exclude_user_ids):
            if trust_preferred_without_role:
                return user
            has_role = (
                db.query(UserRole)
                .filter(
                    UserRole.user_id == user.id,
                    UserRole.role_id == role_id,
                    UserRole.is_active == True,  # noqa: E712
                )
                .first()
            )
            if has_role:
                return user
    return assign_user(db, role_id, exclude_user_ids=exclude_user_ids)


def assign_user(
    db: Session,
    role_id: int,
    *,
    exclude_user_ids: set[int] | None = None,
):

    rule = db.query(AssignmentRule).filter_by(role_id=role_id, is_active=True).first()

    users = (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(
            UserRole.role_id == role_id,
            UserRole.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
        .all()
    )

    if exclude_user_ids:
        users = [u for u in users if u.id not in exclude_user_ids]

    if not users:
        return None

    # =========================
    # STRATEGY: RANDOM
    # =========================
    if not rule or rule.strategy == "random":
        return random.choice(users)

    # =========================
    # STRATEGY: LEAST LOADED
    # =========================
    if rule.strategy == "least_loaded":
        user_loads = []

        for u in users:
            count = (
                db.query(func.count(InboxItem.id))
                .filter(InboxItem.user_id == u.id, InboxItem.is_done == False)
                .scalar()
            )
            user_loads.append((u, count))

        user_loads.sort(key=lambda x: x[1])
        return user_loads[0][0]

    # =========================
    # STRATEGY: ROUND ROBIN
    # =========================
    if rule.strategy == "round_robin":
        last = (
            db.query(InboxItem.user_id)
            .filter(InboxItem.role_id == role_id)
            .order_by(InboxItem.id.desc())
            .first()
        )

        if last:
            user_ids = [u.id for u in users]
            if last[0] in user_ids:
                idx = user_ids.index(last[0])
                return users[(idx + 1) % len(users)]

        return users[0]

    return users[0]
