from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import MASTERDATA_VIEW
from app.dependencies.auth import require_any_permission, require_permission
from app.services.master_data.warehouse import *

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])


@router.post("/")
def create(
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("masterdata.manage")),
):
    return create_warehouse(db, payload["name"])


@router.get("/")
def list_all(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*MASTERDATA_VIEW)),
):
    offset = (page - 1) * page_size
    items = list_warehouses(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    total = count_warehouses(
        db, filter_by=filter_by, filter_value=filter_value, search=search
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{wh_id}")
def get_one(
    wh_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*MASTERDATA_VIEW)),
):
    return get_warehouse(db, wh_id)


@router.put("/{wh_id}")
def update(
    wh_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("masterdata.manage")),
):
    return update_warehouse(db, wh_id, payload)


@router.delete("/{wh_id}")
def delete(
    wh_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("masterdata.manage")),
):
    return delete_warehouse(db, wh_id)
