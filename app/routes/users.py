from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.schemas.user_list import UserCreate, UserListItem, UserListResponse, UserUpdate
from app.services.user_list import (
    count_users,
    create_user_admin,
    delete_user_admin,
    get_user_list_item,
    list_users,
    update_user_admin,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserListItem, status_code=201)
def create_user_api(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return create_user_admin(db, payload)


@router.get("/", response_model=UserListResponse)
def list_users_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    id: int | None = Query(None, alias="id"),
    username: str | None = Query(None),
    email: str | None = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    offset = (page - 1) * page_size
    items = list_users(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        user_id=id,
        username=username,
        email=email,
        search=search,
    )
    total = count_users(
        db,
        user_id=id,
        username=username,
        email=email,
        search=search,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.get("/{user_id}", response_model=UserListItem)
def get_user_api(
    user_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    item = get_user_list_item(db, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    return item


@router.put("/{user_id}", response_model=UserListItem)
@router.patch("/{user_id}", response_model=UserListItem)
def update_user_api(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return update_user_admin(db, user_id, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_api(
    user_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    delete_user_admin(db, user_id)
