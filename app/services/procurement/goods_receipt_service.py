"""رسید ورود کالا از فاکتور خرید — ثبت، نگاشت کالا، ورود به انبار."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.procurement import (
    GRN_STATUS_CANCELLED,
    GRN_STATUS_DRAFT,
    GRN_STATUS_POSTED,
    PROFORMA_STATUS_APPROVED,
    REQUEST_TYPE_PURCHASE,
    STATUS_COMPLETED,
    STATUS_READY_FOR_PAYMENT,
    STATUS_RECEIVING,
)
from app.models.item import Item
from app.models.procurement.goods_receipt import GoodsReceipt, GoodsReceiptLine
from app.models.procurement.proforma import ProcurementProforma
from app.models.procurement.supplier import Supplier
from app.models.request import Request
from app.models.request_item import RequestItem
from app.models.warehouse import Warehouse
from app.models.category import Category
from app.services.attachment_service import (
    ENTITY_GOODS_RECEIPT,
    list_attachments,
    save_entity_attachment,
    serialize_attachment,
)
from app.services.inventory.transaction import _apply_stock_in
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def _next_grn_no(db: Session) -> str:
    count = db.query(func.count(GoodsReceipt.id)).scalar() or 0
    year = datetime.utcnow().year
    return f"GRN-{year}-{count + 1:05d}"


def _default_category_id(db: Session) -> int:
    row = db.query(Category).order_by(Category.id).first()
    if row:
        return row.id
    cat = Category(name="عمومی")
    db.add(cat)
    db.flush()
    return cat.id


def resolve_item_id_for_line(
    db: Session,
    *,
    item_id: int | None,
    item_name: str | None,
) -> int:
    if item_id:
        item = db.get(Item, item_id)
        if item:
            return item.id

    name = (item_name or "").strip()
    if not name:
        raise ValueError("برای هر قلم باید کالا انتخاب یا نام کالا مشخص شود")

    existing = db.query(Item).filter(func.lower(Item.name) == name.lower()).first()
    if existing:
        return existing.id

    sku_base = "".join(c for c in name[:20] if c.isalnum()) or "ITEM"
    sku = f"{sku_base}-{datetime.utcnow().strftime('%H%M%S')}"
    while db.query(Item).filter(Item.sku == sku).first():
        sku = f"{sku_base}-{datetime.utcnow().strftime('%H%M%S%f')[:8]}"

    item = Item(name=name, sku=sku, category_id=_default_category_id(db))
    db.add(item)
    db.flush()
    return item.id


def _approved_proforma(db: Session, request_id: int) -> ProcurementProforma | None:
    return (
        db.query(ProcurementProforma)
        .filter(
            ProcurementProforma.request_id == request_id,
            ProcurementProforma.status == PROFORMA_STATUS_APPROVED,
        )
        .order_by(ProcurementProforma.id.desc())
        .first()
    )


def serialize_grn(db: Session, grn: GoodsReceipt) -> dict:
    supplier = db.get(Supplier, grn.supplier_id)
    warehouse = db.get(Warehouse, grn.warehouse_id)
    request = db.get(Request, grn.request_id)
    atts = list_attachments(db, ENTITY_GOODS_RECEIPT, grn.id)
    att = serialize_attachment(atts[0]) if atts else {}
    lines_out = []
    for line in grn.lines:
        item = db.get(Item, line.item_id)
        ri = db.get(RequestItem, line.request_item_id) if line.request_item_id else None
        lines_out.append(
            {
                "id": line.id,
                "request_item_id": line.request_item_id,
                "item_id": line.item_id,
                "item_name": item.name if item else (ri.item_name if ri else None),
                "quantity_received": line.quantity_received,
                "unit_price": float(line.unit_price) if line.unit_price is not None else None,
            }
        )
    return {
        "id": grn.id,
        "grn_no": grn.grn_no,
        "request_id": grn.request_id,
        "supplier_id": grn.supplier_id,
        "supplier_name": supplier.name if supplier else None,
        "warehouse_id": grn.warehouse_id,
        "warehouse_name": warehouse.name if warehouse else None,
        "proforma_id": grn.proforma_id,
        "status": grn.status,
        "invoice_notes": grn.invoice_notes,
        "receipt_date": grn.receipt_date,
        "created_at": grn.created_at,
        "posted_at": grn.posted_at,
        "lines": lines_out,
        "request_status": request.status if request else None,
        "file_name": att.get("file_name"),
        "download_url": att.get("download_url") or att.get("url"),
    }


def create_goods_receipt(
    db: Session,
    *,
    request_id: int,
    warehouse_id: int,
    user_id: int,
    supplier_id: int | None = None,
    receipt_date: date | None = None,
    invoice_notes: str | None = None,
    lines: list[dict] | None = None,
) -> dict:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        raise ValueError("درخواست خرید یافت نشد")
    if req.status not in (STATUS_RECEIVING, STATUS_COMPLETED):
        raise ValueError(
            "رسید انبار فقط پس از تأیید پرداخت (وضعیت «در حال دریافت انبار») قابل ثبت است"
        )

    warehouse = db.get(Warehouse, warehouse_id)
    if not warehouse:
        raise ValueError("انبار مقصد یافت نشد")

    proforma = _approved_proforma(db, request_id)
    resolved_supplier_id = supplier_id or (proforma.supplier_id if proforma else None)
    if not resolved_supplier_id:
        raise ValueError("تأمین‌کننده مشخص نیست؛ پیش‌فاکتور تأییدشده یا supplier_id لازم است")

    supplier = db.get(Supplier, resolved_supplier_id)
    if not supplier:
        raise ValueError("تأمین‌کننده یافت نشد")

    existing_draft = (
        db.query(GoodsReceipt)
        .filter(
            GoodsReceipt.request_id == request_id,
            GoodsReceipt.status == GRN_STATUS_DRAFT,
        )
        .first()
    )
    if existing_draft:
        raise ValueError(
            f"برای این درخواست رسید پیش‌نویس (شماره {existing_draft.grn_no or existing_draft.id}) وجود دارد"
        )

    grn = GoodsReceipt(
        grn_no=_next_grn_no(db),
        request_id=request_id,
        supplier_id=resolved_supplier_id,
        warehouse_id=warehouse_id,
        proforma_id=proforma.id if proforma else None,
        status=GRN_STATUS_DRAFT,
        invoice_notes=(invoice_notes or "").strip() or None,
        receipt_date=receipt_date or date.today(),
        created_by=user_id,
    )
    db.add(grn)
    db.flush()

    request_items = (
        db.query(RequestItem).filter(RequestItem.request_id == request_id).all()
    )
    line_inputs = lines or []
    if line_inputs:
        for row in line_inputs:
            ri_id = row.get("request_item_id")
            ri = db.get(RequestItem, ri_id) if ri_id else None
            qty = int(row.get("quantity_received") or row.get("quantity") or 0)
            if qty <= 0:
                raise ValueError("تعداد دریافتی باید بیشتر از صفر باشد")
            item_id = resolve_item_id_for_line(
                db,
                item_id=row.get("item_id"),
                item_name=row.get("item_name") or (ri.item_name if ri else None),
            )
            if ri and ri.item_id is None:
                ri.item_id = item_id
            db.add(
                GoodsReceiptLine(
                    grn_id=grn.id,
                    request_item_id=ri_id,
                    item_id=item_id,
                    quantity_received=qty,
                    unit_price=row.get("unit_price"),
                )
            )
    else:
        for ri in request_items:
            qty = ri.quantity
            item_id = resolve_item_id_for_line(
                db,
                item_id=ri.item_id,
                item_name=ri.item_name,
            )
            if ri.item_id is None:
                ri.item_id = item_id
            db.add(
                GoodsReceiptLine(
                    grn_id=grn.id,
                    request_item_id=ri.id,
                    item_id=item_id,
                    quantity_received=qty,
                )
            )

    db.flush()
    line_count = (
        db.query(func.count(GoodsReceiptLine.id))
        .filter(GoodsReceiptLine.grn_id == grn.id)
        .scalar()
        or 0
    )
    if line_count == 0:
        raise ValueError("هیچ قلمی برای رسید ثبت نشد")

    req.status = STATUS_RECEIVING
    db.commit()
    db.refresh(grn)
    return serialize_grn(db, grn)


async def upload_grn_invoice(
    db: Session,
    grn_id: int,
    *,
    user_id: int,
    file: UploadFile,
) -> dict:
    grn = db.get(GoodsReceipt, grn_id)
    if not grn:
        raise ValueError("رسید یافت نشد")
    if grn.status != GRN_STATUS_DRAFT:
        raise ValueError("فقط رسید پیش‌نویس قابل ویرایش است")

    await save_entity_attachment(
        db,
        entity_type=ENTITY_GOODS_RECEIPT,
        entity_id=grn.id,
        uploaded_by_id=user_id,
        file=file,
    )
    db.commit()
    db.refresh(grn)
    return serialize_grn(db, grn)


def update_goods_receipt(
    db: Session,
    grn_id: int,
    *,
    warehouse_id: int | None = None,
    invoice_notes: str | None = None,
    receipt_date: date | None = None,
    lines: list[dict] | None = None,
) -> dict:
    grn = db.get(GoodsReceipt, grn_id)
    if not grn:
        raise ValueError("رسید یافت نشد")
    if grn.status != GRN_STATUS_DRAFT:
        raise ValueError("فقط رسید پیش‌نویس قابل ویرایش است")

    if warehouse_id is not None:
        if not db.get(Warehouse, warehouse_id):
            raise ValueError("انبار یافت نشد")
        grn.warehouse_id = warehouse_id
    if invoice_notes is not None:
        grn.invoice_notes = invoice_notes.strip() or None
    if receipt_date is not None:
        grn.receipt_date = receipt_date

    if lines is not None:
        db.query(GoodsReceiptLine).filter(GoodsReceiptLine.grn_id == grn_id).delete()
        for row in lines:
            ri_id = row.get("request_item_id")
            ri = db.get(RequestItem, ri_id) if ri_id else None
            qty = int(row.get("quantity_received") or 0)
            if qty <= 0:
                raise ValueError("تعداد دریافتی باید بیشتر از صفر باشد")
            item_id = resolve_item_id_for_line(
                db,
                item_id=row.get("item_id"),
                item_name=row.get("item_name") or (ri.item_name if ri else None),
            )
            if ri and ri.item_id is None:
                ri.item_id = item_id
            db.add(
                GoodsReceiptLine(
                    grn_id=grn.id,
                    request_item_id=ri_id,
                    item_id=item_id,
                    quantity_received=qty,
                    unit_price=row.get("unit_price"),
                )
            )

    db.commit()
    db.refresh(grn)
    return serialize_grn(db, grn)


def post_goods_receipt(db: Session, grn_id: int, *, user_id: int) -> dict:
    grn = db.get(GoodsReceipt, grn_id)
    if not grn:
        raise ValueError("رسید یافت نشد")
    if grn.status != GRN_STATUS_DRAFT:
        raise ValueError("این رسید قبلاً ثبت نهایی شده است")

    atts = list_attachments(db, ENTITY_GOODS_RECEIPT, grn.id)
    if not atts:
        raise ValueError("فایل فاکتور خرید باید ضمیمه شود")

    if not grn.lines:
        raise ValueError("رسید بدون قلم کالا قابل ثبت نیست")

    for line in grn.lines:
        if line.quantity_received <= 0:
            raise ValueError("تعداد دریافتی نامعتبر است")
        _apply_stock_in(
            db,
            line.item_id,
            grn.warehouse_id,
            line.quantity_received,
            ref_type="goods_receipt",
            ref_id=grn.id,
            user_id=user_id,
        )

    grn.status = GRN_STATUS_POSTED
    grn.posted_at = datetime.utcnow()
    grn.posted_by = user_id

    req = db.get(Request, grn.request_id)
    if req:
        req.status = STATUS_COMPLETED

    db.commit()
    db.refresh(grn)
    return serialize_grn(db, grn)


def get_goods_receipt(db: Session, grn_id: int) -> dict | None:
    grn = db.get(GoodsReceipt, grn_id)
    return serialize_grn(db, grn) if grn else None


def list_goods_receipts(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    request_id: int | None = None,
) -> list[dict]:
    query = db.query(GoodsReceipt)
    if request_id:
        query = query.filter(GoodsReceipt.request_id == request_id)
    query = apply_equal_filter(query, GoodsReceipt, filter_by, filter_value)
    query = apply_search_filter(query, GoodsReceipt, search, ["grn_no", "status"])
    query = apply_sort(query, GoodsReceipt, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [serialize_grn(db, r) for r in rows]


def count_goods_receipts(
    db: Session,
    *,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    request_id: int | None = None,
) -> int:
    query = db.query(func.count(GoodsReceipt.id))
    if request_id:
        query = query.filter(GoodsReceipt.request_id == request_id)
    query = apply_equal_filter(query, GoodsReceipt, filter_by, filter_value)
    query = apply_search_filter(query, GoodsReceipt, search, ["grn_no", "status"])
    return query.scalar() or 0


def cancel_goods_receipt(db: Session, grn_id: int) -> dict:
    grn = db.get(GoodsReceipt, grn_id)
    if not grn:
        raise ValueError("رسید یافت نشد")
    if grn.status == GRN_STATUS_POSTED:
        raise ValueError("رسید ثبت‌شده قابل لغو نیست")
    grn.status = GRN_STATUS_CANCELLED
    db.commit()
    db.refresh(grn)
    return serialize_grn(db, grn)
