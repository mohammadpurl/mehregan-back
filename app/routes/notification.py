from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import NOTIFICATIONS
from app.dependencies.auth import require_any_permission

from app.services.feed_serialize import serialize_notification_items
from app.services.notification import (
    count_user_notifications,
    get_notifications_grouped,
    get_user_notifications_paginated,
    get_user_notifications,
    get_unread_count,
    mark_all_as_read,
    mark_as_read,
    update_notification,
)
from app.schemas.notification import NotificationOut, NotificationUpdate

router = APIRouter(prefix="/notifications")


@router.get("/")
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    include_total: bool = Query(True, alias="includeTotal"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    offset = (page - 1) * page_size
    items = get_user_notifications(
        db,
        user.id,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    total = (
        count_user_notifications(
            db,
            user.id,
            filter_by=filter_by,
            filter_value=filter_value,
            search=search,
        )
        if include_total
        else None
    )
    return {
        "items": serialize_notification_items(db, items),
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.get("/unread-count", response_model=dict)
def unread_count(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    return {"count": get_unread_count(db, user.id)}


@router.put("/{notification_id}", response_model=NotificationOut)
@router.patch("/{notification_id}", response_model=NotificationOut)
def update_notification_api(
    notification_id: int,
    payload: NotificationUpdate | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    """فرانت: PUT /notifications/{id} با body اختیاری { \"isRead\": true }."""
    is_read = True if payload is None or payload.is_read is None else payload.is_read
    row = update_notification(db, notification_id, user.id, is_read=is_read)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="اعلان یافت نشد",
        )
    return row


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    row = mark_as_read(db, notification_id, user.id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="اعلان یافت نشد",
        )
    return row


@router.get("/list", response_model=None)
def list_notifications_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    return get_user_notifications_paginated(
        db,
        user.id,
        page,
        page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )


@router.post("/read-all")
def read_all(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    mark_all_as_read(db, user.id)
    return {"status": "ok"}


@router.get("/grouped")
def grouped_notifications(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    return get_notifications_grouped(db, user.id)
