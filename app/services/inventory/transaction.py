from sqlalchemy.orm import Session

from app.models.inventory_transaction import InventoryTransaction
from app.services.inventory.stock_service import get_or_create_stock


# =========================
# STOCK IN
# =========================
def _apply_stock_in(
    db: Session,
    item_id: int,
    warehouse_id: int,
    qty: int,
    *,
    ref_type: str | None = None,
    ref_id: int | None = None,
    user_id: int | None = None,
) -> InventoryTransaction:
    stock = get_or_create_stock(db, item_id, warehouse_id)
    tx = InventoryTransaction(
        item_id=item_id,
        warehouse_id=warehouse_id,
        type="IN",
        quantity=qty,
        ref_type=ref_type,
        ref_id=ref_id,
        created_by=user_id,
    )
    stock.quantity += qty
    db.add(tx)
    return tx


def stock_in(
    db: Session,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref_type: str | None = None,
    ref_id: int | None = None,
    user_id: int | None = None,
):
    tx = _apply_stock_in(
        db,
        item_id,
        warehouse_id,
        qty,
        ref_type=ref_type,
        ref_id=ref_id,
        user_id=user_id,
    )
    db.commit()
    return tx


# =========================
# STOCK OUT
# =========================
def stock_out(
    db: Session,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref_type: str | None = None,
    ref_id: int | None = None,
    user_id: int | None = None,
):

    stock = get_or_create_stock(db, item_id, warehouse_id)

    if stock.quantity < qty:
        raise Exception("Insufficient stock")

    tx = InventoryTransaction(
        item_id=item_id,
        warehouse_id=warehouse_id,
        type="OUT",
        quantity=qty,
        ref_type=ref_type,
        ref_id=ref_id,
        created_by=user_id,
    )

    stock.quantity -= qty

    db.add(tx)
    db.commit()

    return tx


# =========================
# TRANSFER
# =========================
def transfer(
    db: Session,
    item_id: int,
    from_warehouse_id: int,
    to_warehouse_id: int,
    qty: int,
    ref_type: str | None = None,
    ref_id: int | None = None,
    user_id: int | None = None,
):

    # خروج از انبار مبدا
    stock_out(
        db,
        item_id,
        from_warehouse_id,
        qty,
        ref_type,
        ref_id,
        user_id,
    )

    # ورود به انبار مقصد
    stock_in(
        db,
        item_id,
        to_warehouse_id,
        qty,
        ref_type,
        ref_id,
        user_id,
    )

    return {"status": "transferred"}
