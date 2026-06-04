from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.notification import Notification
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    type: str,
    ref_id: int,
    ref_type: str,
):
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        ref_id=ref_id,
        ref_type=ref_type,
        is_read=False,
    )

    db.add(notif)
    db.flush()
    return notif


# ==============================
# GET USER NOTIFICATIONS
# ==============================
def get_user_notifications(
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
    query = db.query(Notification).filter(Notification.user_id == user_id)
    query = apply_equal_filter(query, Notification, filter_by, filter_value)
    query = apply_search_filter(query, Notification, search, ["title", "message", "type", "ref_type"])
    query = apply_sort(query, Notification, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


# ==============================
# UNREAD COUNT
# ==============================
def get_unread_count(db: Session, user_id: int):
    return (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
        .scalar()
    )


# ==============================
# MARK AS READ
# ==============================
def _get_user_notification(
    db: Session, notification_id: int, user_id: int
) -> Notification | None:
    return (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        .first()
    )


def mark_as_read(db: Session, notification_id: int, user_id: int):
    return update_notification(
        db, notification_id, user_id, is_read=True
    )


def update_notification(
    db: Session,
    notification_id: int,
    user_id: int,
    *,
    is_read: bool | None = None,
) -> Notification | None:
    notif = _get_user_notification(db, notification_id, user_id)
    if not notif:
        return None
    if is_read is not None:
        notif.is_read = is_read
    db.commit()
    db.refresh(notif)
    return notif


def get_user_notifications_paginated(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    offset = (page - 1) * page_size

    items = get_user_notifications(
        db,
        user_id,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    total = count_user_notifications(db, user_id, filter_by, filter_value, search)

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def count_user_notifications(
    db: Session,
    user_id: int,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(Notification.id)).filter(Notification.user_id == user_id)
    query = apply_equal_filter(query, Notification, filter_by, filter_value)
    query = apply_search_filter(query, Notification, search, ["title", "message", "type", "ref_type"])
    return query.scalar() or 0


def mark_all_as_read(db: Session, user_id: int):
    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).update({"is_read": True})

    db.commit()


def delete_notifications_for_workflow(db: Session, instance_id: int) -> int:
    """حذف اعلان‌های مرتبط با یک نمونه workflow (تأیید/رد)."""
    count = (
        db.query(Notification)
        .filter(
            Notification.ref_type == "workflow",
            Notification.ref_id == instance_id,
        )
        .delete(synchronize_session=False)
    )
    return count or 0


def get_notifications_grouped(db: Session, user_id: int):
    rows = (
        db.query(Notification.type, func.count(Notification.id))
        .filter(Notification.user_id == user_id)
        .group_by(Notification.type)
        .all()
    )

    return {r[0]: r[1] for r in rows}
