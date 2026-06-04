from sqlalchemy.orm import Session

from app.models.procurement.purchase_order import PurchaseOrder
from app.services.inventory.transaction import stock_in


def receive_po(db: Session, po_id: int, warehouse_id: int, user_id: int):

    po = db.get(PurchaseOrder, po_id)

    if not po:
        return

    for item in po.items:
        stock_in(
            db=db,
            item_id=item.item_id,
            warehouse_id=warehouse_id,
            qty=item.quantity,
            ref_type="po",
            ref_id=po_id,
            user_id=user_id,
        )

    po.status = "received"
    db.commit()
