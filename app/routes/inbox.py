from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import INBOX_READ, WORKFLOW_APPROVE
from app.dependencies.auth import require_any_permission
from app.services.feed_serialize import serialize_inbox_items
from app.services.inbox import (
    count_user_inbox,
    count_user_inbox_unread,
    get_user_inbox,
    mark_as_read,
    mark_as_done,
)

router = APIRouter(prefix="/inbox", tags=["Inbox"])


@router.get("/unread-count")
def inbox_unread_count(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*INBOX_READ)),
):
    return {"count": count_user_inbox_unread(db, user.id)}


@router.get("/")
def my_inbox(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    include_total: bool = Query(True, alias="includeTotal"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*INBOX_READ)),
):
    offset = (page - 1) * page_size
    items = get_user_inbox(
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
        count_user_inbox(
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
        "items": serialize_inbox_items(db, items),
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.post("/{inbox_id}/read")
def read_inbox(
    inbox_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*INBOX_READ)),
):
    return mark_as_read(db, inbox_id)


@router.post("/{inbox_id}/done")
def done_inbox(
    inbox_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_APPROVE)),
):
    return mark_as_done(db, inbox_id)
