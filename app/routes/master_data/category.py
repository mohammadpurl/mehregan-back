from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.category import (
    CategoryCreate,
    CategoryListResponse,
    CategoryOut,
    CategoryTreeNode,
    CategoryUpdate,
)
from app.services.master_data import category as category_service

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("/", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("item.create")),
):
    try:
        return category_service.create_category(db, payload.name, payload.parent_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/", response_model=CategoryListResponse)
def list_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("asc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    parent_id: int | None = Query(None, alias="parentId"),
    roots_only: bool = Query(False, alias="rootsOnly"),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("item.read")),
):
    offset = (page - 1) * page_size
    items = category_service.list_categories(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        parent_id=parent_id,
        roots_only=roots_only,
    )
    total = category_service.count_categories(
        db,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        parent_id=parent_id,
        roots_only=roots_only,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/tree", response_model=list[CategoryTreeNode])
def list_category_tree(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("item.read")),
):
    return category_service.list_category_tree(db)


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("item.read")),
):
    item = category_service.get_category(db, category_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="گروه کالا یافت نشد")
    return item


@router.put("/{category_id}", response_model=CategoryOut)
@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("item.update")),
):
    try:
        data = payload.model_dump(exclude_unset=True)
        updated = category_service.update_category(
            db,
            category_id,
            name=data.get("name"),
            parent_id=data.get("parent_id"),
            parent_id_set="parent_id" in data,
        )
    except ValueError as err:
        raise_from_value_error(err)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="گروه کالا یافت نشد")
    return updated


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("item.delete")),
):
    try:
        deleted = category_service.delete_category(db, category_id)
    except ValueError as err:
        raise_from_value_error(err)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="گروه کالا یافت نشد")
