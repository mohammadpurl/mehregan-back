from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission

from app.schemas.item import ItemCreate, ItemListResponse, ItemResponse, ItemUpdate
from app.services.master_data import item as item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/", response_model=ItemResponse)
def create_item(
    payload: ItemCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("item.create")),
):
    return item_service.create_item(db, payload, user)


@router.get("/", response_model=ItemListResponse)
def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_permission("item.read")),
):
    offset = (page - 1) * page_size
    items = item_service.get_items(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    total = item_service.count_items(
        db,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_permission("item.read")),
):
    return item_service.get_item(db, item_id)


@router.put("/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("item.update")),
):
    item = item_service.get_item_entity(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="کالا یافت نشد")
    return item_service.update_item(db, item, payload, user)


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_permission("item.delete")),
):
    item = item_service.get_item_entity(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="کالا یافت نشد")
    item_service.delete_item(db, item)
    return {"message": "deleted"}


@router.post("/{item_id}/submit")
def submit_item(
    item_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_permission("item.submit")),
):
    item = item_service.get_item_entity(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="کالا یافت نشد")
    return item_service.change_item_status(db, item, "submitted", user)
