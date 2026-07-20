from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.constants.api_permissions import PROCUREMENT_READ, PROCUREMENT_WRITE
from app.core.database import get_db
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.procurement import (
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
)
from app.services.procurement.purchase_order_service import (
    count_purchase_orders,
    create_purchase_order,
    delete_purchase_order,
    get_purchase_order,
    list_purchase_orders,
    update_purchase_order,
)

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"])


@router.get("/")
def list_purchase_orders_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    request_id: str | None = Query(None, alias="request_id"),
    supplier_name: str | None = Query(None, alias="supplier_name"),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    offset = (page - 1) * page_size
    items = list_purchase_orders(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        request_id=request_id,
        supplier_name=supplier_name,
        status=status,
    )
    total = count_purchase_orders(
        db,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        request_id=request_id,
        supplier_name=supplier_name,
        status=status,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.post("/", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order_api(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return create_purchase_order(
            db,
            supplier_name=payload.supplier_name,
            request_id=payload.request_id,
            item_name=payload.item_name,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            expected_date=payload.expected_date,
            status=payload.status,
            description=payload.description,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{po_id}", response_model=PurchaseOrderOut)
def get_purchase_order_api(
    po_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    row = get_purchase_order(db, po_id)
    if not row:
        raise_from_value_error(ValueError("purchase order not found"))
    return row


@router.put("/{po_id}", response_model=PurchaseOrderOut)
@router.patch("/{po_id}", response_model=PurchaseOrderOut)
def update_purchase_order_api(
    po_id: int,
    payload: PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        data = payload.model_dump(exclude_unset=True)
        return update_purchase_order(db, po_id, **data)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order_api(
    po_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        delete_purchase_order(db, po_id)
    except ValueError as err:
        raise_from_value_error(err)
