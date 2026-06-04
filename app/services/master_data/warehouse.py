from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.warehouse import Warehouse
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


# =========================
# CREATE WAREHOUSE
# =========================
def create_warehouse(db: Session, name: str):

    wh = Warehouse(name=name)

    db.add(wh)
    db.commit()
    db.refresh(wh)

    return wh


# =========================
# LIST
# =========================
def list_warehouses(
    db: Session,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(Warehouse)
    query = apply_equal_filter(query, Warehouse, filter_by, filter_value)
    query = apply_search_filter(query, Warehouse, search, ["name"])
    query = apply_sort(query, Warehouse, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_warehouses(
    db: Session,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(Warehouse.id))
    query = apply_equal_filter(query, Warehouse, filter_by, filter_value)
    query = apply_search_filter(query, Warehouse, search, ["name"])
    return query.scalar() or 0


# =========================
# GET
# =========================
def get_warehouse(db: Session, wh_id: int):

    return db.get(Warehouse, wh_id)


# =========================
# UPDATE
# =========================
def update_warehouse(db: Session, wh_id: int, data: dict):

    wh = db.get(Warehouse, wh_id)

    if not wh:
        return None

    for k, v in data.items():
        setattr(wh, k, v)

    db.commit()
    db.refresh(wh)

    return wh


# =========================
# DELETE
# =========================
def delete_warehouse(db: Session, wh_id: int):

    wh = db.get(Warehouse, wh_id)

    if not wh:
        return False

    db.delete(wh)
    db.commit()

    return True
