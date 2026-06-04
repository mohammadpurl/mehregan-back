"""خلاصه روزانه انبار."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory_transaction import InventoryTransaction
from app.models.item import Item
from app.models.procurement.goods_receipt import GoodsReceipt
from app.models.stock import Stock
from app.models.warehouse import Warehouse


LOW_STOCK_THRESHOLD = 5


def get_warehouse_daily_report(
    db: Session,
    *,
    report_date: date | None = None,
    warehouse_id: int | None = None,
) -> dict:
    d = report_date or date.today()
    day_start = datetime.combine(d, time.min)
    day_end = datetime.combine(d, time.max)

    tx_q = db.query(InventoryTransaction).filter(
        InventoryTransaction.created_at >= day_start,
        InventoryTransaction.created_at <= day_end,
    )
    if warehouse_id:
        tx_q = tx_q.filter(InventoryTransaction.warehouse_id == warehouse_id)

    tx_rows = tx_q.all()
    by_type: dict[str, dict] = {}
    for tx in tx_rows:
        t = (tx.type or "UNKNOWN").upper()
        bucket = by_type.setdefault(t, {"count": 0, "quantity": 0})
        bucket["count"] += 1
        bucket["quantity"] += int(tx.quantity or 0)

    grn_q = db.query(GoodsReceipt).filter(
        GoodsReceipt.created_at >= day_start,
        GoodsReceipt.created_at <= day_end,
    )
    if warehouse_id:
        grn_q = grn_q.filter(GoodsReceipt.warehouse_id == warehouse_id)
    grn_today = grn_q.count()
    grn_posted_today = grn_q.filter(GoodsReceipt.posted_at.isnot(None)).count()

    stock_q = (
        db.query(
            Stock.id,
            Stock.item_id,
            Stock.warehouse_id,
            Stock.quantity,
            Item.name,
            Item.sku,
            Warehouse.name.label("warehouse_name"),
        )
        .join(Item, Item.id == Stock.item_id)
        .join(Warehouse, Warehouse.id == Stock.warehouse_id)
    )
    if warehouse_id:
        stock_q = stock_q.filter(Stock.warehouse_id == warehouse_id)

    low_stock = []
    for row in stock_q.all():
        qty = int(row.quantity or 0)
        if qty <= LOW_STOCK_THRESHOLD:
            low_stock.append(
                {
                    "stock_id": row.id,
                    "item_id": row.item_id,
                    "item_name": row.name,
                    "sku": row.sku,
                    "warehouse_id": row.warehouse_id,
                    "warehouse_name": row.warehouse_name,
                    "quantity": qty,
                }
            )

    warehouse_count = db.query(func.count(Warehouse.id)).scalar() or 0
    stock_count_q = db.query(func.count(Stock.id))
    if warehouse_id:
        stock_count_q = stock_count_q.filter(Stock.warehouse_id == warehouse_id)
    total_skus = stock_count_q.scalar() or 0

    return {
        "date": d.isoformat(),
        "warehouse_id": warehouse_id,
        "warehouses_count": warehouse_count,
        "stock_lines_count": total_skus,
        "transactions_today": {
            "total": len(tx_rows),
            "by_type": by_type,
        },
        "grn": {
            "created_today": grn_today,
            "posted_today": grn_posted_today,
        },
        "low_stock": low_stock[:50],
        "low_stock_count": len(low_stock),
    }
