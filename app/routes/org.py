from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.services.org_hierarchy import get_org_hierarchy, get_user_org_position

router = APIRouter(prefix="/org", tags=["Organization"])


@router.get("/hierarchy")
def org_hierarchy_api(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    """درخت واحدهای سازمانی + لیست کاربران با مدیر مستقیم و واحد."""
    return get_org_hierarchy(db)


@router.get("/users/{user_id}/position")
def user_org_position_api(
    user_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    pos = get_user_org_position(db, user_id)
    if not pos:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    return pos
