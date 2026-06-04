from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.api_error import api_error_detail
from app.models.category import Category
from app.models.item import Item
from app.services.audit import create_audit_log
from app.services.query_utils import apply_equal_filter, apply_search_filter
from app.services.workflow import can_transition

SORT_FIELD_MAP = {
    "category_name": "category_name",
    "categoryName": "category_name",
    "code": "sku",
}


def _item_code(item: Item) -> str:
    return getattr(item, "sku", None) or getattr(item, "code", "") or ""


def serialize_item(item: Item, category_name: str | None = None) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "code": _item_code(item),
        "category_id": item.category_id,
        "category_name": category_name,
        "unit": getattr(item, "unit", None),
    }


def create_item(db, data, user):
    item = Item(
        name=data.name,
        sku=data.code,
        category_id=data.category_id,
    )

    db.add(item)
    db.flush()

    create_audit_log(
        db,
        action="create",
        user_id=user.id,
        entity="item",
        entity_id=item.id,
        new_data={
            "name": item.name,
            "code": _item_code(item),
            "category_id": item.category_id,
        },
    )

    db.commit()
    db.refresh(item)
    return serialize_item(item, _category_name(db, item.category_id))


def _category_name(db: Session, category_id: int | None) -> str | None:
    if not category_id:
        return None
    category = db.get(Category, category_id)
    return category.name if category else None


def _resolve_sort_column(sort_by: str, Category_model):
    mapped = SORT_FIELD_MAP.get(sort_by, sort_by)
    if mapped == "category_name":
        return Category_model.name
    column = getattr(Item, mapped, None)
    return column or Item.id


def get_items(
    db: Session,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(Item, Category.name.label("category_name")).outerjoin(
        Category, Item.category_id == Category.id
    )
    query = apply_equal_filter(query, Item, filter_by, filter_value)
    query = apply_search_filter(query, Item, search, ["name", "sku"])
    sort_col = _resolve_sort_column(sort_by, Category)
    if str(sort_order).lower() == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())
    rows = query.offset(offset).limit(limit).all()
    return [serialize_item(item, category_name) for item, category_name in rows]


def count_items(
    db: Session,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(Item.id))
    query = apply_equal_filter(query, Item, filter_by, filter_value)
    query = apply_search_filter(query, Item, search, ["name", "sku"])
    return query.scalar() or 0


def get_item_entity(db: Session, item_id: int) -> Item | None:
    return db.get(Item, item_id)


def get_item(db: Session, item_id: int):
    row = (
        db.query(Item, Category.name.label("category_name"))
        .outerjoin(Category, Item.category_id == Category.id)
        .filter(Item.id == item_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=api_error_detail("NOT_FOUND", "کالا یافت نشد"),
        )
    item, category_name = row
    return serialize_item(item, category_name)


def update_item(db, item, data, user):
    old = {
        "name": item.name,
        "code": _item_code(item),
        "category_id": item.category_id,
    }

    updates = data.model_dump(exclude_unset=True)
    if "code" in updates:
        item.sku = updates.pop("code")
    for key, value in updates.items():
        setattr(item, key, value)

    db.flush()

    create_audit_log(
        db,
        action="update",
        user_id=user.id,
        entity="item",
        entity_id=item.id,
        old_data=old,
        new_data=updates,
    )

    db.commit()
    return serialize_item(item, _category_name(db, item.category_id))


def delete_item(db: Session, item: Item):
    db.delete(item)
    db.commit()


def change_item_status(db, item, new_state, user):
    current = item.workflow_state.code

    if not can_transition(current, new_state):
        raise Exception("transition not allowed")

    item.workflow_state_id = new_state

    create_audit_log(
        db,
        action="status_change",
        user_id=user.id,
        entity="item",
        entity_id=item.id,
        old_data={"state": current},
        new_data={"state": new_state},
    )

    db.commit()
