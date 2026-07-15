from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import NOTIFICATIONS
from app.dependencies.auth import require_any_permission
from app.dependencies.pagination import ListQueryParams, get_list_params
from app.services.notification_center import (
    get_bell_unread_count,
    get_notification_center,
    get_notification_feed,
)

router = APIRouter(prefix="/notification-center")


@router.get("/unread-count")
def notification_center_unread_count(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    """شمارش badge زنگ بدون دوبل‌شماری inbox+notification یکسان."""
    return {"count": get_bell_unread_count(db, user.id)}


@router.get("/feed")
def notification_feed(
    limit: int = Query(8, ge=1, le=30),
    enrich: bool = Query(False, description="غنی‌سازی متن workflow (کندتر)"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    """لیست سبک برای dropdown اعلان — یک درخواست به‌جای چند API جدا."""
    return get_notification_feed(db, user.id, limit=limit, enrich=enrich)


@router.get("/")
def notification_center(
    params: ListQueryParams = Depends(get_list_params),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*NOTIFICATIONS)),
):
    data = get_notification_center(
        db,
        user.id,
        offset=params.offset,
        limit=params.page_size,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )
    return {
        **data,
        "page": params.page,
        "pageSize": params.page_size,
        "sortBy": params.sort_by,
        "sortOrder": params.sort_order,
    }
