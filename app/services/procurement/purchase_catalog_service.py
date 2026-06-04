"""کاتالوگ کالا برای فرم درخواست خرید.

منبع نام کالا: جدول ``items`` (فرم / master کالا).
موجودی انبار: جدول ``stocks`` (رابطه item + warehouse + quantity).
اگر برای کالایی رکورد stock نباشد، موجودی ۰ نمایش داده می‌شود.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.item import Item
from app.models.stock import Stock
from app.models.warehouse import Warehouse


def _serialize_row(
    item: Item,
    *,
    on_hand: int,
    warehouse_id: int | None,
    warehouse_name: str | None,
) -> dict:
    return {
        "item_id": item.id,
        "item_name": item.name,
        "sku": getattr(item, "sku", None) or getattr(item, "code", None),
        "unit": getattr(item, "unit", None),
        "warehouse_id": warehouse_id,
        "warehouse_name": warehouse_name,
        "on_hand": on_hand,
        "has_stock_record": on_hand > 0,
    }


def _stock_totals_by_item(
    db: Session, *, warehouse_id: int | None
) -> dict[int, int]:
    q = db.query(Stock.item_id, func.coalesce(func.sum(Stock.quantity), 0)).group_by(
        Stock.item_id
    )
    if warehouse_id is not None:
        q = q.filter(Stock.warehouse_id == warehouse_id)
    return {int(item_id): int(qty or 0) for item_id, qty in q.all()}


def list_purchase_warehouse_catalog(
    db: Session,
    *,
    warehouse_id: int | None = None,
    search: str | None = None,
    limit: int = 500,
) -> dict:
    warehouses = [
        {"id": w.id, "name": w.name}
        for w in db.query(Warehouse).order_by(Warehouse.name.asc()).all()
    ]

    item_q = db.query(Item).order_by(Item.name.asc())
    if search and search.strip():
        term = f"%{search.strip()}%"
        item_q = item_q.filter(or_(Item.name.ilike(term), Item.sku.ilike(term)))

    stock_map = _stock_totals_by_item(db, warehouse_id=warehouse_id)
    wh_label: Warehouse | None = None
    if warehouse_id is not None:
        wh_label = db.get(Warehouse, warehouse_id)
    elif len(warehouses) == 1:
        wh_label = db.get(Warehouse, warehouses[0]["id"])

    items = [
        _serialize_row(
            item,
            on_hand=stock_map.get(item.id, 0),
            warehouse_id=wh_label.id if wh_label else None,
            warehouse_name=wh_label.name if wh_label else None,
        )
        for item in item_q.limit(limit).all()
    ]

    return {
        "warehouses": warehouses,
        "items": items,
        "meta": {
            "item_source": "items",
            "stock_source": "stocks",
            "total_items": len(items),
        },
    }
