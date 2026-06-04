from sqlalchemy.orm import Session

from app.models.request import Request
from app.models.request_item import RequestItem

from app.services.inventory.transaction import stock_out


def handle_request_approved(db: Session, request_id: int, user_id: int):

    request = db.get(Request, request_id)

    if not request:
        return

    items = db.query(RequestItem).filter(RequestItem.request_id == request_id).all()

    for item in items:
        stock_out(
            db=db,
            item_id=item.item_id,
            warehouse_id=request.warehouse_id,
            qty=item.quantity,
            ref_type="request",
            ref_id=request_id,
            user_id=user_id,
        )

    request.status = "approved"
    db.commit()
