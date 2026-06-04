from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies.crud_http import EntityInUseError
from app.models.category import Category
from app.models.item import Item
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def _validate_parent(db: Session, parent_id: int | None, category_id: int | None = None) -> None:
    if parent_id is None:
        return
    if category_id is not None and parent_id == category_id:
        raise ValueError("گروه نمی‌تواند والد خودش باشد")
    parent = db.get(Category, parent_id)
    if not parent:
        raise ValueError("گروه والد یافت نشد")
    if category_id is None:
        return
    current_parent_id = parent_id
    visited = {category_id}
    while current_parent_id is not None:
        if current_parent_id in visited:
            raise ValueError("انتخاب این والد باعث حلقه در درخت گروه‌ها می‌شود")
        visited.add(current_parent_id)
        ancestor = db.get(Category, current_parent_id)
        if not ancestor:
            break
        current_parent_id = ancestor.parent_id


def _serialize_category(db: Session, category: Category) -> dict:
    parent_name = None
    if category.parent_id:
        parent = db.get(Category, category.parent_id)
        parent_name = parent.name if parent else None
    children_count = (
        db.query(func.count(Category.id)).filter_by(parent_id=category.id).scalar() or 0
    )
    items_count = (
        db.query(func.count(Item.id)).filter_by(category_id=category.id).scalar() or 0
    )
    return {
        "id": category.id,
        "name": category.name,
        "parent_id": category.parent_id,
        "parent_name": parent_name,
        "children_count": children_count,
        "items_count": items_count,
    }


def create_category(db: Session, name: str, parent_id: int | None = None) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("نام گروه الزامی است")
    _validate_parent(db, parent_id)

    exists = db.query(Category).filter(Category.name == name, Category.parent_id == parent_id).first()
    if exists:
        raise ValueError("گروهی با این نام در همین سطح قبلاً ثبت شده است")

    category = Category(name=name, parent_id=parent_id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return _serialize_category(db, category)


def get_category(db: Session, category_id: int) -> dict | None:
    category = db.get(Category, category_id)
    if not category:
        return None
    return _serialize_category(db, category)


def list_categories(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    parent_id: int | None = None,
    roots_only: bool = False,
):
    query = db.query(Category)
    if roots_only:
        query = query.filter(Category.parent_id.is_(None))
    elif parent_id is not None:
        query = query.filter(Category.parent_id == parent_id)
    query = apply_equal_filter(query, Category, filter_by, filter_value)
    query = apply_search_filter(query, Category, search, ["name"])
    query = apply_sort(query, Category, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [_serialize_category(db, row) for row in rows]


def count_categories(
    db: Session,
    *,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
    parent_id: int | None = None,
    roots_only: bool = False,
) -> int:
    query = db.query(func.count(Category.id))
    if roots_only:
        query = query.filter(Category.parent_id.is_(None))
    elif parent_id is not None:
        query = query.filter(Category.parent_id == parent_id)
    query = apply_equal_filter(query, Category, filter_by, filter_value)
    query = apply_search_filter(query, Category, search, ["name"])
    return query.scalar() or 0


def list_category_tree(db: Session) -> list[dict]:
    categories = db.query(Category).order_by(Category.name.asc()).all()
    nodes: dict[int, dict] = {
        c.id: {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "children": [],
        }
        for c in categories
    }
    roots: list[dict] = []
    for category in categories:
        node = nodes[category.id]
        if category.parent_id and category.parent_id in nodes:
            nodes[category.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def update_category(
    db: Session,
    category_id: int,
    *,
    name: str | None = None,
    parent_id: int | None = None,
    parent_id_set: bool = False,
) -> dict | None:
    category = db.get(Category, category_id)
    if not category:
        return None

    new_name = category.name if name is None else name.strip()
    if not new_name:
        raise ValueError("نام گروه الزامی است")

    new_parent_id = category.parent_id
    if parent_id_set:
        new_parent_id = parent_id
    _validate_parent(db, new_parent_id, category_id=category_id)

    sibling = (
        db.query(Category)
        .filter(
            Category.name == new_name,
            Category.parent_id == new_parent_id,
            Category.id != category_id,
        )
        .first()
    )
    if sibling:
        raise ValueError("گروهی با این نام در همین سطح قبلاً ثبت شده است")

    category.name = new_name
    category.parent_id = new_parent_id
    db.commit()
    db.refresh(category)
    return _serialize_category(db, category)


def delete_category(db: Session, category_id: int) -> bool:
    category = db.get(Category, category_id)
    if not category:
        return False

    children_count = (
        db.query(func.count(Category.id)).filter_by(parent_id=category_id).scalar() or 0
    )
    if children_count:
        raise EntityInUseError(
            f"این گروه دارای {children_count} زیرگروه است و قابل حذف نیست",
            code="CATEGORY_HAS_CHILDREN",
            children_count=children_count,
            category_id=category_id,
        )

    items_count = (
        db.query(func.count(Item.id)).filter_by(category_id=category_id).scalar() or 0
    )
    if items_count:
        raise EntityInUseError(
            f"این گروه در {items_count} کالا استفاده شده و قابل حذف نیست",
            code="CATEGORY_HAS_ITEMS",
            items_count=items_count,
            category_id=category_id,
        )

    db.delete(category)
    db.commit()
    return True
