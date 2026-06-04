from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.services.master_data.stock import *

router = APIRouter(prefix="/stocks", tags=["Stock"])


@router.get("/")
def get(
    item_id: int,
    warehouse_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.read")),
):
    return get_stock(db, item_id, warehouse_id)


@router.post("/increase")
def inc(
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.transfer")),
):
    return increase_stock(
        db, payload["item_id"], payload["warehouse_id"], payload["qty"]
    )


@router.post("/decrease")
def dec(
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("inventory.transfer")),
):
    return decrease_stock(
        db, payload["item_id"], payload["warehouse_id"], payload["qty"]
    )
