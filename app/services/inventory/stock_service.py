from sqlalchemy.orm import Session

from app.models.stock import Stock


def get_or_create_stock(db: Session, item_id: int, warehouse_id: int):

    stock = (
        db.query(Stock).filter_by(item_id=item_id, warehouse_id=warehouse_id).first()
    )

    if not stock:
        stock = Stock(
            item_id=item_id,
            warehouse_id=warehouse_id,
            quantity=0,
        )
        db.add(stock)
        db.flush()  # مهم

    return stock
