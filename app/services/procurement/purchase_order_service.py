"""سفارش خرید (PO) — CRUD برای فرانت."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.item import Item
from app.models.procurement.purchase_order import PurchaseOrder
from app.models.procurement.purchase_order_item import PurchaseOrderItem
from app.models.procurement.supplier import Supplier
from app.models.request import Request
from app.models.request_item import RequestItem
from app.services.procurement.goods_receipt_service import resolve_item_id_for_line
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def _next_order_no(db: Session) -> str:
    count = db.query(func.count(PurchaseOrder.id)).scalar() or 0
    return f"PO-{datetime.utcnow().year}-{count + 1:05d}"


def _get_or_create_supplier(db: Session, name: str) -> Supplier:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("نام تأمین‌کننده الزامی است")
    row = (
        db.query(Supplier)
        .filter(func.lower(Supplier.name) == trimmed.lower())
        .first()
    )
    if row:
        return row
    row = Supplier(name=trimmed, is_active=True)
    db.add(row)
    db.flush()
    return row


def _parse_request_id(value: str | int | None) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    return date.fromisoformat(s[:10])


def serialize_purchase_order(db: Session, po: PurchaseOrder) -> dict:
    supplier = db.get(Supplier, po.supplier_id)
    item_name = po.item_name
    quantity = po.quantity
    if not item_name and po.items:
        first = po.items[0]
        if first.item_id:
            item = db.get(Item, first.item_id)
            item_name = item.name if item else item_name
        quantity = quantity or first.quantity
    return {
        "id": po.id,
        "order_no": po.order_no,
        "request_id": str(po.request_id) if po.request_id is not None else None,
        "supplier_name": supplier.name if supplier else "",
        "item_name": item_name,
        "quantity": quantity,
        "unit_price": float(po.unit_price) if po.unit_price is not None else None,
        "expected_date": po.expected_date.isoformat() if po.expected_date else None,
        "status": po.status,
        "description": po.description,
        "created_at": po.created_at,
    }


def list_purchase_orders(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    request_id: str | None = None,
    supplier_name: str | None = None,
    status: str | None = None,
) -> list[dict]:
    query = db.query(PurchaseOrder)

    rid = _parse_request_id(request_id)
    if rid is not None:
        query = query.filter(PurchaseOrder.request_id == rid)
    if supplier_name and supplier_name.strip():
        query = query.join(Supplier).filter(
            Supplier.name.ilike(f"%{supplier_name.strip()}%")
        )
    if status and status.strip():
        query = query.filter(PurchaseOrder.status == status.strip())

    if filter_by and filter_value:
        if filter_by == "request_id":
            parsed = _parse_request_id(filter_value)
            if parsed is not None:
                query = query.filter(PurchaseOrder.request_id == parsed)
        elif filter_by == "supplier_name":
            query = query.join(Supplier).filter(
                Supplier.name.ilike(f"%{str(filter_value).strip()}%")
            )
        elif filter_by == "status":
            query = query.filter(PurchaseOrder.status == str(filter_value).strip())
        else:
            query = apply_equal_filter(query, PurchaseOrder, filter_by, filter_value)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.outerjoin(Supplier).filter(
            or_(
                PurchaseOrder.order_no.ilike(term),
                PurchaseOrder.item_name.ilike(term),
                PurchaseOrder.description.ilike(term),
                Supplier.name.ilike(term),
            )
        )

    sort_map = {
        "request_id": PurchaseOrder.request_id,
        "supplier_name": Supplier.name,
        "status": PurchaseOrder.status,
        "expected_date": PurchaseOrder.expected_date,
    }
    if sort_by in sort_map and sort_by == "supplier_name":
        query = query.join(Supplier, isouter=True)
        col = sort_map[sort_by]
        query = query.order_by(col.desc() if sort_order == "desc" else col.asc())
    else:
        query = apply_sort(query, PurchaseOrder, sort_by, sort_order)

    rows = query.offset(offset).limit(limit).all()
    return [serialize_purchase_order(db, r) for r in rows]


def count_purchase_orders(
    db: Session,
    *,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    request_id: str | None = None,
    supplier_name: str | None = None,
    status: str | None = None,
) -> int:
    query = db.query(func.count(PurchaseOrder.id))
    rid = _parse_request_id(request_id)
    if rid is not None:
        query = query.filter(PurchaseOrder.request_id == rid)
    if supplier_name and supplier_name.strip():
        query = query.join(Supplier).filter(
            Supplier.name.ilike(f"%{supplier_name.strip()}%")
        )
    if status and status.strip():
        query = query.filter(PurchaseOrder.status == status.strip())
    if filter_by and filter_value:
        if filter_by == "request_id":
            parsed = _parse_request_id(filter_value)
            if parsed is not None:
                query = query.filter(PurchaseOrder.request_id == parsed)
        elif filter_by == "supplier_name":
            query = query.join(Supplier).filter(
                Supplier.name.ilike(f"%{str(filter_value).strip()}%")
            )
        elif filter_by == "status":
            query = query.filter(PurchaseOrder.status == str(filter_value).strip())
        else:
            query = apply_equal_filter(query, PurchaseOrder, filter_by, filter_value)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.outerjoin(Supplier).filter(
            or_(
                PurchaseOrder.order_no.ilike(term),
                PurchaseOrder.item_name.ilike(term),
                PurchaseOrder.description.ilike(term),
                Supplier.name.ilike(term),
            )
        )
    return query.scalar() or 0


def get_purchase_order(db: Session, po_id: int) -> dict | None:
    po = db.get(PurchaseOrder, po_id)
    return serialize_purchase_order(db, po) if po else None


def create_purchase_order(
    db: Session,
    *,
    supplier_name: str,
    request_id: str | int | None = None,
    item_name: str | None = None,
    quantity: int | None = None,
    unit_price: float | None = None,
    expected_date: str | date | None = None,
    status: str = "draft",
    description: str | None = None,
) -> dict:
    supplier = _get_or_create_supplier(db, supplier_name)
    rid = _parse_request_id(request_id)
    if rid is not None and not db.get(Request, rid):
        raise ValueError("درخواست خرید مرتبط یافت نشد")

    po = PurchaseOrder(
        order_no=_next_order_no(db),
        supplier_id=supplier.id,
        request_id=rid,
        item_name=(item_name or "").strip() or None,
        quantity=quantity,
        unit_price=unit_price,
        expected_date=_parse_date(expected_date),
        description=(description or "").strip() or None,
        status=status or "draft",
    )
    db.add(po)
    db.flush()

    if po.item_name and po.quantity and po.quantity > 0:
        item_id = resolve_item_id_for_line(db, item_id=None, item_name=po.item_name)
        db.add(
            PurchaseOrderItem(
                po_id=po.id,
                item_id=item_id,
                quantity=po.quantity,
            )
        )

    db.commit()
    db.refresh(po)
    return serialize_purchase_order(db, po)


def update_purchase_order(
    db: Session,
    po_id: int,
    *,
    supplier_name: str | None = None,
    request_id: str | int | None = None,
    item_name: str | None = None,
    quantity: int | None = None,
    unit_price: float | None = None,
    expected_date: str | date | None = None,
    status: str | None = None,
    description: str | None = None,
) -> dict:
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise ValueError("سفارش خرید یافت نشد")
    if po.status in ("closed", "cancelled", "received"):
        raise ValueError("این سفارش قابل ویرایش نیست")

    if supplier_name is not None:
        po.supplier_id = _get_or_create_supplier(db, supplier_name).id
    if request_id is not None:
        rid = _parse_request_id(request_id)
        if rid is not None and not db.get(Request, rid):
            raise ValueError("درخواست خرید مرتبط یافت نشد")
        po.request_id = rid
    if item_name is not None:
        po.item_name = item_name.strip() or None
    if quantity is not None:
        po.quantity = quantity
    if unit_price is not None:
        po.unit_price = unit_price
    if expected_date is not None:
        po.expected_date = _parse_date(expected_date)
    if status is not None:
        po.status = status
    if description is not None:
        po.description = description.strip() or None

    if po.item_name and po.quantity and po.quantity > 0:
        db.query(PurchaseOrderItem).filter(PurchaseOrderItem.po_id == po_id).delete()
        item_id = resolve_item_id_for_line(db, item_id=None, item_name=po.item_name)
        db.add(
            PurchaseOrderItem(
                po_id=po.id,
                item_id=item_id,
                quantity=po.quantity,
            )
        )

    db.commit()
    db.refresh(po)
    return serialize_purchase_order(db, po)


def delete_purchase_order(db: Session, po_id: int) -> None:
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise ValueError("سفارش خرید یافت نشد")
    if po.status == "received":
        raise ValueError("سفارش دریافت‌شده قابل حذف نیست")
    db.delete(po)
    db.commit()


def ensure_purchase_order_for_request(
    db: Session, request_id: int, supplier_id: int
) -> PurchaseOrder:
    """اگر PO برای درخواست نیست، از روی اقلام درخواست می‌سازد."""
    from app.models.request import Request

    req = db.get(Request, request_id)
    if not req:
        raise ValueError("درخواست یافت نشد")
    if req.purchase_order_id:
        existing = db.get(PurchaseOrder, req.purchase_order_id)
        if existing:
            return existing
    row = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.request_id == request_id)
        .order_by(PurchaseOrder.id.desc())
        .first()
    )
    if row:
        req.purchase_order_id = row.id
        db.commit()
        return row
    po = create_po_from_request(db, request_id, supplier_id)
    req.purchase_order_id = po.id
    db.commit()
    return po


def create_po_from_request(db: Session, request_id: int, supplier_id: int) -> PurchaseOrder:
    """ساخت PO از درخواست خرید (برای یکپارچگی قدیمی)."""
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError("تأمین‌کننده یافت نشد")

    request_items = (
        db.query(RequestItem).filter(RequestItem.request_id == request_id).all()
    )
    first_name = request_items[0].item_name if request_items else None
    total_qty = sum(ri.quantity for ri in request_items) if request_items else None

    po = PurchaseOrder(
        order_no=_next_order_no(db),
        supplier_id=supplier_id,
        request_id=request_id,
        item_name=first_name,
        quantity=total_qty,
        status="pending",
    )
    db.add(po)
    db.flush()

    for item in request_items:
        item_id = resolve_item_id_for_line(
            db, item_id=item.item_id, item_name=item.item_name
        )
        if item.item_id is None:
            item.item_id = item_id
        db.add(
            PurchaseOrderItem(
                po_id=po.id,
                item_id=item_id,
                quantity=item.quantity,
            )
        )

    db.commit()
    db.refresh(po)
    return po
