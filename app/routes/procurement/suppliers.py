from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.constants.api_permissions import PROCUREMENT_READ, PROCUREMENT_WRITE
from app.core.database import get_db
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.procurement import SupplierCreate, SupplierOut, SupplierUpdate
from app.services.procurement.supplier_service import (
    count_suppliers,
    create_supplier,
    delete_supplier,
    get_supplier,
    list_suppliers,
    update_supplier,
)

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.post("/", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier_api(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return create_supplier(db, payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/")
def list_suppliers_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    active_only: bool = Query(False, alias="activeOnly"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    offset = (page - 1) * page_size
    items = list_suppliers(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        active_only=active_only,
    )
    total = count_suppliers(
        db,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        active_only=active_only,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier_api(
    supplier_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    row = get_supplier(db, supplier_id)
    if not row:
        raise_from_value_error(ValueError("supplier not found"))
    return row


@router.get("/{supplier_id}/proformas")
def list_supplier_proformas_api(
    supplier_id: int,
    include_archived: bool = Query(True, alias="includeArchived"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    from app.services.procurement.proforma_service import list_proformas_for_supplier

    return list_proformas_for_supplier(db, supplier_id, include_archived=include_archived)


@router.put("/{supplier_id}", response_model=SupplierOut)
@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier_api(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return update_supplier(db, supplier_id, payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_api(
    supplier_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        delete_supplier(db, supplier_id)
    except ValueError as err:
        raise_from_value_error(err)
