from sqlalchemy.orm import Session

from app.models.inbox import InboxItem
from app.models.notification import Notification
from app.services.feed_serialize import (
    serialize_inbox_items,
    serialize_notification_items,
)
from app.services.inbox import count_user_inbox_unread, get_user_inbox
from app.services.notification import get_unread_count, get_user_notifications
from app.services.query_utils import apply_sort


def get_notification_center(
    db: Session,
    user_id: int,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    notif_query = db.query(Notification).filter(Notification.user_id == user_id)
    notif_query = apply_sort(notif_query, Notification, sort_by, sort_order)
    notifications = notif_query.offset(offset).limit(limit).all()

    inbox_query = db.query(InboxItem).filter(InboxItem.user_id == user_id)
    inbox_query = apply_sort(inbox_query, InboxItem, sort_by, sort_order)
    inbox = inbox_query.offset(offset).limit(limit).all()

    return {
        "notifications": notifications,
        "inbox": inbox,
    }


def get_notification_feed(
    db: Session,
    user_id: int,
    *,
    limit: int = 8,
    enrich: bool = False,
) -> dict:
    """یک پاسخ برای dropdown زنگ — بدون شمارش total و با enrich اختیاری."""
    cap = max(1, min(int(limit), 30))
    inbox_rows = get_user_inbox(
        db,
        user_id,
        offset=0,
        limit=cap,
        sort_by="created_at",
        sort_order="desc",
    )
    notification_rows = get_user_notifications(
        db,
        user_id,
        offset=0,
        limit=cap,
        sort_by="created_at",
        sort_order="desc",
    )
    return {
        "inbox": serialize_inbox_items(db, inbox_rows, enrich=enrich),
        "notifications": serialize_notification_items(db, notification_rows, enrich=enrich),
        "inboxUnread": count_user_inbox_unread(db, user_id),
        "notificationUnread": int(get_unread_count(db, user_id) or 0),
    }
