from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inbox import InboxItem
from app.services.assignment import resolve_assignee_for_role
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def find_open_workflow_inbox(
    db: Session,
    *,
    instance_id: int,
    user_id: int,
) -> InboxItem | None:
    return (
        db.query(InboxItem)
        .filter(
            InboxItem.ref_type == "workflow",
            InboxItem.ref_id == instance_id,
            InboxItem.user_id == user_id,
            InboxItem.is_done == False,  # noqa: E712
        )
        .order_by(InboxItem.id.desc())
        .first()
    )


def create_inbox_item(
    db,
    role_id,
    title,
    message,
    ref_id,
    ref_type,
    preferred_user_id: int | None = None,
):
    """
    اگر preferred_user_id از گردش‌کار آمده باشد، همان کاربر را استفاده کن
    (مثلاً مدیر مستقیم بدون نقش manager در RBAC). در غیر این صورت از استخر نقش.
    """
    user = None
    if preferred_user_id is not None:
        from app.models.user import User

        preferred = db.get(User, preferred_user_id)
        if preferred and preferred.is_active:
            user = preferred
    if user is None and role_id is not None:
        user = resolve_assignee_for_role(db, role_id, preferred_user_id)

    inbox = InboxItem(
        user_id=user.id if user else None,
        role_id=role_id,
        title=title,
        message=message,
        ref_id=ref_id,
        ref_type=ref_type,
    )

    db.add(inbox)
    db.flush()

    return inbox


def mark_as_read(db: Session, inbox_id: int):
    item = db.query(InboxItem).get(inbox_id)
    if not item:
        return None

    item.is_read = True
    item.read_at = datetime.utcnow()
    db.commit()
    return item


def mark_as_done(db: Session, inbox_id: int):
    item = db.query(InboxItem).get(inbox_id)
    if not item:
        return None

    item.is_done = True
    db.commit()
    return item


def mark_inbox_done_for_ad_hoc_task(
    db: Session,
    task_id: int,
    *,
    user_id: int | None = None,
) -> int:
    """علامت‌گذاری آیتم‌های کارتابل مرتبط با یک کار پیش‌بینی‌نشده به‌عنوان انجام‌شده."""
    query = db.query(InboxItem).filter(
        InboxItem.ref_type == "ad_hoc_task",
        InboxItem.ref_id == task_id,
        InboxItem.is_done == False,  # noqa: E712
    )
    if user_id is not None:
        query = query.filter(InboxItem.user_id == user_id)
    updated = 0
    for item in query.all():
        item.is_done = True
        updated += 1
    if updated:
        db.flush()
    return updated


def mark_inbox_done_for_workflow(
    db: Session,
    instance_id: int,
    *,
    user_id: int | None = None,
) -> int:
    """علامت‌گذاری آیتم‌های کارتابل مرتبط با یک نمونه workflow به‌عنوان انجام‌شده."""
    query = db.query(InboxItem).filter(
        InboxItem.ref_type == "workflow",
        InboxItem.ref_id == instance_id,
        InboxItem.is_done == False,  # noqa: E712
    )
    if user_id is not None:
        query = query.filter(InboxItem.user_id == user_id)
    updated = 0
    for item in query.all():
        item.is_done = True
        updated += 1
    if updated:
        db.flush()
    return updated


def get_user_inbox(
    db: Session,
    user_id: int,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(InboxItem).filter_by(user_id=user_id, is_done=False)
    query = apply_equal_filter(query, InboxItem, filter_by, filter_value)
    query = apply_search_filter(query, InboxItem, search, ["title", "message", "ref_type"])
    query = apply_sort(query, InboxItem, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def get_role_inbox(db: Session, role_id: int, offset: int = 0, limit: int = 20):
    return (
        db.query(InboxItem)
        .filter_by(role_id=role_id)
        .order_by(InboxItem.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_user_inbox_unread(db: Session, user_id: int) -> int:
    return (
        db.query(func.count(InboxItem.id))
        .filter(
            InboxItem.user_id == user_id,
            InboxItem.is_done == False,  # noqa: E712
            InboxItem.is_read == False,  # noqa: E712
        )
        .scalar()
        or 0
    )


def count_user_inbox(
    db: Session,
    user_id: int,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(InboxItem.id)).filter(
        InboxItem.user_id == user_id,
        InboxItem.is_done == False,  # noqa: E712
    )
    query = apply_equal_filter(query, InboxItem, filter_by, filter_value)
    query = apply_search_filter(query, InboxItem, search, ["title", "message", "ref_type"])
    return query.scalar() or 0
