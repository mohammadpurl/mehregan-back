from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies.crud_http import EntityInUseError
from app.models.department import Department
from app.models.user import User
from app.services.query_utils import apply_search_filter, apply_sort


def _user_display_name(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def _validate_parent(
    db: Session, parent_id: int | None, department_id: int | None = None
) -> None:
    if parent_id is None:
        return
    if department_id is not None and parent_id == department_id:
        raise ValueError("واحد سازمانی نمی‌تواند والد خودش باشد")
    parent = db.get(Department, parent_id)
    if not parent:
        raise ValueError("واحد والد یافت نشد")
    if department_id is None:
        return
    current_parent_id = parent_id
    visited = {department_id}
    while current_parent_id is not None:
        if current_parent_id in visited:
            raise ValueError("انتخاب این والد باعث حلقه در سلسله‌مراتب می‌شود")
        visited.add(current_parent_id)
        ancestor = db.get(Department, current_parent_id)
        if not ancestor:
            break
        current_parent_id = ancestor.parent_id


def _serialize_department(db: Session, dept: Department) -> dict:
    parent_name = None
    if dept.parent_id:
        parent = db.get(Department, dept.parent_id)
        parent_name = parent.name if parent else None
    head_name = None
    if getattr(dept, "head_user_id", None):
        head_name = _user_display_name(db.get(User, dept.head_user_id))
    children_count = (
        db.query(func.count(Department.id)).filter_by(parent_id=dept.id).scalar() or 0
    )
    users_count = (
        db.query(func.count(User.id)).filter_by(department_id=dept.id).scalar() or 0
    )
    return {
        "id": dept.id,
        "name": dept.name,
        "parent_id": dept.parent_id,
        "parent_name": parent_name,
        "head_user_id": getattr(dept, "head_user_id", None),
        "head_user_name": head_name,
        "children_count": children_count,
        "users_count": users_count,
    }


def create_department(
    db: Session,
    name: str,
    parent_id: int | None = None,
    head_user_id: int | None = None,
) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("نام واحد الزامی است")
    _validate_parent(db, parent_id)
    if head_user_id is not None and not db.get(User, head_user_id):
        raise ValueError("مسئول واحد یافت نشد")

    dept = Department(name=name, parent_id=parent_id, head_user_id=head_user_id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return _serialize_department(db, dept)


def update_department(
    db: Session,
    department_id: int,
    *,
    name: str | None = None,
    parent_id: int | None = None,
    head_user_id: int | None = None,
    unset_head: bool = False,
) -> dict:
    dept = db.get(Department, department_id)
    if not dept:
        raise ValueError("واحد سازمانی یافت نشد")

    if name is not None:
        dept.name = name.strip()
    if parent_id is not None:
        _validate_parent(db, parent_id, department_id=department_id)
        dept.parent_id = parent_id
    if unset_head:
        dept.head_user_id = None
    elif head_user_id is not None:
        if not db.get(User, head_user_id):
            raise ValueError("مسئول واحد یافت نشد")
        dept.head_user_id = head_user_id

    db.commit()
    db.refresh(dept)
    return _serialize_department(db, dept)


def delete_department(db: Session, department_id: int) -> None:
    dept = db.get(Department, department_id)
    if not dept:
        raise ValueError("واحد سازمانی یافت نشد")
    child_count = (
        db.query(func.count(Department.id)).filter_by(parent_id=department_id).scalar()
        or 0
    )
    if child_count:
        raise EntityInUseError(
            "ابتدا زیرمجموعه‌های واحد را حذف یا منتقل کنید",
            code="DEPARTMENT_HAS_CHILDREN",
        )
    user_count = (
        db.query(func.count(User.id)).filter_by(department_id=department_id).scalar() or 0
    )
    if user_count:
        raise EntityInUseError(
            "کاربرانی به این واحد متصل هستند",
            code="DEPARTMENT_HAS_USERS",
        )
    db.delete(dept)
    db.commit()


def get_department(db: Session, department_id: int) -> dict | None:
    dept = db.get(Department, department_id)
    if not dept:
        return None
    return _serialize_department(db, dept)


def list_departments(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "asc",
    search: str | None = None,
    parent_id: int | None = None,
    roots_only: bool = False,
) -> list[dict]:
    query = db.query(Department)
    if roots_only:
        query = query.filter(Department.parent_id.is_(None))
    elif parent_id is not None:
        query = query.filter(Department.parent_id == parent_id)
    query = apply_search_filter(query, Department, search, ["name"])
    query = apply_sort(query, Department, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [_serialize_department(db, d) for d in rows]


def count_departments(
    db: Session,
    *,
    search: str | None = None,
    parent_id: int | None = None,
    roots_only: bool = False,
) -> int:
    query = db.query(func.count(Department.id))
    if roots_only:
        query = query.filter(Department.parent_id.is_(None))
    elif parent_id is not None:
        query = query.filter(Department.parent_id == parent_id)
    query = apply_search_filter(query, Department, search, ["name"])
    return query.scalar() or 0


def build_department_tree(db: Session) -> list[dict]:
    all_depts = db.query(Department).order_by(Department.name).all()
    serialized = {d.id: _serialize_department(db, d) for d in all_depts}
    nodes: dict[int, dict] = {
        did: {**data, "children": []} for did, data in serialized.items()
    }
    roots: list[dict] = []
    for did, node in nodes.items():
        parent_id = node.get("parent_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots
