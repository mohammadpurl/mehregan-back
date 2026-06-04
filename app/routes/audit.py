from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_any_permission
from app.services.audit_list import count_audit_logs, list_audit_logs

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("/")
def list_audit_logs_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    entity: str | None = Query(None),
    entity_id: int | None = Query(None, alias="entityId"),
    user_id: int | None = Query(None, alias="userId"),
    action: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission("admin.manage")),
):
    offset = (page - 1) * page_size
    items = list_audit_logs(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        entity=entity,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        search=search,
    )
    total = count_audit_logs(
        db,
        entity=entity,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        search=search,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}
