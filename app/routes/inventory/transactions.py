from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission

from app.services.inventory.transaction import (
    stock_in,
    stock_out,
    transfer,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post("/in")
def stock_in_api(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_permission("inventory.transfer")),
):
    return stock_in(
        db=db,
        item_id=payload["item_id"],
        warehouse_id=payload["warehouse_id"],
        qty=payload["qty"],
        ref_type=payload.get("ref_type"),
        ref_id=payload.get("ref_id"),
        user_id=payload.get("user_id") or user.id,
    )


@router.post("/out")
def stock_out_api(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_permission("inventory.transfer")),
):
    return stock_out(
        db=db,
        item_id=payload["item_id"],
        warehouse_id=payload["warehouse_id"],
        qty=payload["qty"],
        ref_type=payload.get("ref_type"),
        ref_id=payload.get("ref_id"),
        user_id=payload.get("user_id") or user.id,
    )


@router.post("/transfer")
def transfer_api(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_permission("inventory.transfer")),
):
    return transfer(
        db=db,
        item_id=payload["item_id"],
        from_warehouse_id=payload["from_warehouse_id"],
        to_warehouse_id=payload["to_warehouse_id"],
        qty=payload["qty"],
        ref_type=payload.get("ref_type"),
        ref_id=payload.get("ref_id"),
        user_id=payload.get("user_id") or user.id,
    )
