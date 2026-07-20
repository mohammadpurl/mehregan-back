from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.constants.api_permissions import PROCUREMENT_READ, PROCUREMENT_WRITE
from app.core.database import get_db
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.procurement import (
    CreateGoodsReceiptInput,
    GoodsReceiptOut,
    UpdateGoodsReceiptInput,
)
from app.services.procurement.goods_receipt_service import (
    cancel_goods_receipt,
    count_goods_receipts,
    create_goods_receipt,
    get_goods_receipt,
    list_goods_receipts,
    post_goods_receipt,
    update_goods_receipt,
    upload_grn_invoice,
)
from app.services.master_data.warehouse import list_warehouses, count_warehouses
from app.services.master_data.warehouse import list_warehouses
from app.services.procurement.grn_service import receive_po

router = APIRouter(prefix="/grn", tags=["GRN"])


@router.get("/meta/warehouses")
def warehouses_for_grn_api(
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    rows = list_warehouses(db, offset=0, limit=200, sort_by="name", sort_order="asc")
    return {"items": [{"id": w.id, "name": w.name} for w in rows]}


@router.get("/meta/warehouses")
def list_warehouses_for_grn(
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    items = list_warehouses(db, offset=0, limit=200, sort_by="name", sort_order="asc")
    return {"items": items}


@router.get("/")
def list_grn_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    request_id: int | None = Query(None, alias="requestId"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    offset = (page - 1) * page_size
    items = list_goods_receipts(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        request_id=request_id,
    )
    total = count_goods_receipts(
        db,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
        request_id=request_id,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.post("/", response_model=GoodsReceiptOut, status_code=status.HTTP_201_CREATED)
def create_grn_api(
    payload: CreateGoodsReceiptInput,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        lines = [line.model_dump() for line in payload.lines] if payload.lines else None
        return create_goods_receipt(
            db,
            request_id=payload.request_id,
            warehouse_id=payload.warehouse_id,
            user_id=user.id,
            supplier_id=payload.supplier_id,
            receipt_date=payload.receipt_date,
            invoice_notes=payload.invoice_notes,
            lines=lines,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{grn_id}", response_model=GoodsReceiptOut)
def get_grn_api(
    grn_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    row = get_goods_receipt(db, grn_id)
    if not row:
        raise_from_value_error(ValueError("grn not found"))
    return row


@router.patch("/{grn_id}", response_model=GoodsReceiptOut)
@router.put("/{grn_id}", response_model=GoodsReceiptOut)
def update_grn_api(
    grn_id: int,
    payload: UpdateGoodsReceiptInput,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        data = payload.model_dump(exclude_unset=True)
        lines = data.pop("lines", None)
        if lines is not None:
            lines = [dict(line) for line in lines]
        return update_goods_receipt(db, grn_id, lines=lines, **data)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{grn_id}/invoice", response_model=GoodsReceiptOut)
async def upload_grn_invoice_api(
    grn_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return await upload_grn_invoice(db, grn_id, user_id=user.id, file=file)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{grn_id}/post", response_model=GoodsReceiptOut)
def post_grn_api(
    grn_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return post_goods_receipt(db, grn_id, user_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{grn_id}/cancel", response_model=GoodsReceiptOut)
def cancel_grn_api(
    grn_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return cancel_goods_receipt(db, grn_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/po/{po_id}/receive")
def receive_po_legacy_api(
    po_id: int,
    warehouse_id: int = Query(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    """مسیر قدیمی دریافت از PO — ترجیحاً از POST /grn استفاده کنید."""
    receive_po(db, po_id, warehouse_id, user.id)
    return {"status": "received"}
