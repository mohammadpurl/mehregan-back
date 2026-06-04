from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.procurement.supplier import Supplier
from app.schemas.procurement import SupplierCreate, SupplierUpdate
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def serialize_supplier(row: Supplier) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "phone": row.phone,
        "email": row.email,
        "address": row.address,
        "description": row.description,
        "is_active": row.is_active,
    }


def create_supplier(db: Session, payload: SupplierCreate) -> dict:
    row = Supplier(
        name=payload.name.strip(),
        code=payload.code.strip() if payload.code else None,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_supplier(row)


def update_supplier(db: Session, supplier_id: int, payload: SupplierUpdate) -> dict:
    row = db.get(Supplier, supplier_id)
    if not row:
        raise ValueError("supplier not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        row.name = data["name"].strip()
    for key in ("code", "phone", "email", "address", "description", "is_active"):
        if key in data:
            setattr(row, key, data[key])
    db.commit()
    db.refresh(row)
    return serialize_supplier(row)


def delete_supplier(db: Session, supplier_id: int) -> None:
    row = db.get(Supplier, supplier_id)
    if not row:
        raise ValueError("supplier not found")
    db.delete(row)
    db.commit()


def get_supplier(db: Session, supplier_id: int) -> dict | None:
    row = db.get(Supplier, supplier_id)
    return serialize_supplier(row) if row else None


def list_suppliers(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    active_only: bool = False,
):
    query = db.query(Supplier)
    if active_only:
        query = query.filter(Supplier.is_active == True)  # noqa: E712
    query = apply_equal_filter(query, Supplier, filter_by, filter_value)
    query = apply_search_filter(query, Supplier, search, ["name", "code", "phone", "email"])
    query = apply_sort(query, Supplier, sort_by, sort_order)
    return [serialize_supplier(r) for r in query.offset(offset).limit(limit).all()]


def count_suppliers(
    db: Session,
    *,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    active_only: bool = False,
) -> int:
    query = db.query(func.count(Supplier.id))
    if active_only:
        query = query.filter(Supplier.is_active == True)  # noqa: E712
    query = apply_equal_filter(query, Supplier, filter_by, filter_value)
    query = apply_search_filter(query, Supplier, search, ["name", "code", "phone", "email"])
    return query.scalar() or 0
