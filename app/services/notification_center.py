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


def get_bell_unread_count(db: Session, user_id: int) -> int:
    """
    شمارش badge زنگ: کارتابل خوانده‌نشده + اعلان‌هایی که
    تکراری با همان (ref_type, ref_id) در کارتابل باز/خوانده‌نشده نیستند.
    (هر workflow معمولاً هم inbox و هم notification می‌سازد.)
    """
    inbox_unread = int(count_user_inbox_unread(db, user_id) or 0)

    open_pairs = (
        db.query(InboxItem.ref_type, InboxItem.ref_id)
        .filter(
            InboxItem.user_id == user_id,
            InboxItem.is_done == False,  # noqa: E712
            InboxItem.is_read == False,  # noqa: E712
            InboxItem.ref_id.isnot(None),
            InboxItem.ref_type.isnot(None),
        )
        .all()
    )
    pair_set = {(str(rt), int(rid)) for rt, rid in open_pairs if rid is not None}

    unread_notifs = (
        db.query(Notification.ref_type, Notification.ref_id)
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .all()
    )
    seen_extra: set[tuple[str, int]] = set()
    notif_extra = 0
    for rt, rid in unread_notifs:
        if rid is None or rt is None:
            notif_extra += 1
            continue
        key = (str(rt), int(rid))
        if key in pair_set or key in seen_extra:
            continue
        seen_extra.add(key)
        notif_extra += 1
    return inbox_unread + notif_extra


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
    inbox_unread = int(count_user_inbox_unread(db, user_id) or 0)
    notification_unread = int(get_unread_count(db, user_id) or 0)
    return {
        "inbox": serialize_inbox_items(db, inbox_rows, enrich=enrich),
        "notifications": serialize_notification_items(db, notification_rows, enrich=enrich),
        "inboxUnread": inbox_unread,
        "notificationUnread": notification_unread,
        "totalUnread": get_bell_unread_count(db, user_id),
    }
