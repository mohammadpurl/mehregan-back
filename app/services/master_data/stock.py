from sqlalchemy.orm import Session
from app.models.stock import Stock


# =========================
# GET STOCK
# =========================
def get_stock(db: Session, item_id: int, warehouse_id: int):

    return db.query(Stock).filter_by(item_id=item_id, warehouse_id=warehouse_id).first()


# =========================
# INCREASE STOCK
# =========================
def increase_stock(db: Session, item_id: int, warehouse_id: int, qty: int):

    stock = get_stock(db, item_id, warehouse_id)

    if not stock:
        stock = Stock(item_id=item_id, warehouse_id=warehouse_id, quantity=0)
        db.add(stock)

    stock.quantity += qty

    db.commit()
    db.refresh(stock)

    return stock


# =========================
# DECREASE STOCK
# =========================
def decrease_stock(db: Session, item_id: int, warehouse_id: int, qty: int):

    stock = get_stock(db, item_id, warehouse_id)

    if not stock:
        raise Exception("Stock not found")

    if stock.quantity < qty:
        raise Exception("Insufficient stock")

    stock.quantity -= qty

    db.commit()
    db.refresh(stock)

    return stock
