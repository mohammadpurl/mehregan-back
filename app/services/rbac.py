from sqlalchemy import func, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inbox import InboxItem
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole
from app.models.workflow_step import WorkflowStep
from app.constants.role_labels import ROLE_DISPLAY_NAMES, role_display_name
from app.constants.role_policy import DEFAULT_SINGLETON_ROLE_NAMES
from app.dependencies.crud_http import EntityInUseError
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def _permissions_has_code_column(db: Session) -> bool:
    cols = {c["name"] for c in inspect(db.bind).get_columns("permissions")}
    return "code" in cols


def _permission_search_fields(db: Session) -> list[str]:
    fields = ["name"]
    if _permissions_has_code_column(db):
        fields.append("code")
    return fields


# ======================
# ROLE
# ======================
def get_role(db: Session, role_id: int) -> Role | None:
    return db.get(Role, role_id)


def _role_is_singleton(role: Role) -> bool:
    if getattr(role, "is_singleton", False):
        return True
    return bool(role.name and role.name in DEFAULT_SINGLETON_ROLE_NAMES)


def _assert_singleton_slot_available(
    db: Session, role_id: int, *, for_user_id: int
) -> None:
    role = db.get(Role, role_id)
    if not role or not _role_is_singleton(role):
        return
    other = (
        db.query(UserRole)
        .filter(
            UserRole.role_id == role_id,
            UserRole.is_active == True,  # noqa: E712
            UserRole.user_id != for_user_id,
        )
        .first()
    )
    if other:
        label = role_display_name(role.name, role.display_name)
        raise ValueError(
            f"نقش «{label}» تک‌نفره است و قبلاً به کاربر دیگری اختصاص داده شده است."
        )


def create_role(
    db: Session,
    name: str,
    display_name: str | None = None,
    *,
    is_singleton: bool = False,
):
    name = name.strip()
    exists = db.query(Role).filter_by(name=name).first()
    if exists:
        if display_name and not exists.display_name:
            exists.display_name = display_name.strip()
        if is_singleton:
            exists.is_singleton = True
        db.commit()
        db.refresh(exists)
        return exists

    label = (display_name or ROLE_DISPLAY_NAMES.get(name) or name).strip()
    singleton = is_singleton or name in DEFAULT_SINGLETON_ROLE_NAMES
    role = Role(name=name, display_name=label, is_singleton=singleton)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def update_role(
    db: Session,
    role_id: int,
    *,
    name: str | None = None,
    display_name: str | None = None,
    is_singleton: bool | None = None,
) -> Role:
    role = db.get(Role, role_id)
    if not role:
        raise ValueError("role not found")
    if name is not None:
        name = name.strip()
        other = db.query(Role).filter(Role.name == name, Role.id != role_id).first()
        if other:
            raise ValueError("role name already exists")
        role.name = name
    if display_name is not None:
        role.display_name = display_name.strip() or None
    if is_singleton is not None:
        role.is_singleton = is_singleton
    db.commit()
    db.refresh(role)
    return role


def delete_role(db: Session, role_id: int) -> None:
    role = db.get(Role, role_id)
    if not role:
        raise ValueError("role not found")

    step_count = (
        db.query(func.count(WorkflowStep.id)).filter_by(role_id=role_id).scalar() or 0
    )
    if step_count:
        raise EntityInUseError(
            f"این نقش در {step_count} مرحله گردش‌کار استفاده شده و قابل حذف نیست",
            code="ROLE_IN_USE",
            workflow_step_count=step_count,
            role_id=role_id,
        )

    db.query(InboxItem).filter_by(role_id=role_id).update(
        {InboxItem.role_id: None}, synchronize_session=False
    )
    db.query(RolePermission).filter_by(role_id=role_id).delete()
    db.query(UserRole).filter_by(role_id=role_id).delete()

    try:
        db.delete(role)
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise EntityInUseError(
            "این نقش در بخش دیگری از سیستم استفاده شده و قابل حذف نیست",
            code="ROLE_IN_USE",
            role_id=role_id,
        ) from err


def get_roles(
    db: Session,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(Role)
    query = apply_equal_filter(query, Role, filter_by, filter_value)
    query = apply_search_filter(query, Role, search, ["name", "display_name"])
    query = apply_sort(query, Role, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_roles(
    db: Session,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(Role.id))
    query = apply_equal_filter(query, Role, filter_by, filter_value)
    query = apply_search_filter(query, Role, search, ["name", "display_name"])
    return query.scalar() or 0


# ======================
# PERMISSION
# ======================
def get_permission(db: Session, permission_id: int) -> Permission | None:
    return db.get(Permission, permission_id)


def create_permission(db: Session, code: str, name: str):
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValueError("code and name are required")

    if _permissions_has_code_column(db):
        exists = db.query(Permission).filter_by(code=code).first()
        if not exists:
            exists = db.query(Permission).filter_by(name=name).first()
    else:
        exists = db.query(Permission).filter_by(name=name).first()
    if exists:
        return exists

    values: dict[str, str] = {"name": name}
    if _permissions_has_code_column(db):
        values["code"] = code
    p = Permission(**values)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def get_permissions(
    db: Session,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(Permission)
    query = apply_equal_filter(query, Permission, filter_by, filter_value)
    query = apply_search_filter(
        query, Permission, search, _permission_search_fields(db)
    )
    if sort_by == "code" and not _permissions_has_code_column(db):
        sort_by = "name"
    query = apply_sort(query, Permission, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_permissions(
    db: Session,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(Permission.id))
    query = apply_equal_filter(query, Permission, filter_by, filter_value)
    query = apply_search_filter(
        query, Permission, search, _permission_search_fields(db)
    )
    return query.scalar() or 0


def update_permission(
    db: Session,
    permission_id: int,
    *,
    code: str | None = None,
    name: str | None = None,
) -> Permission:
    perm = db.get(Permission, permission_id)
    if not perm:
        raise ValueError("permission not found")
    if code is not None:
        code = code.strip()
        if not code:
            raise ValueError("code cannot be empty")
        if _permissions_has_code_column(db):
            other = (
                db.query(Permission)
                .filter(Permission.code == code, Permission.id != permission_id)
                .first()
            )
            if other:
                raise ValueError("permission code already exists")
            perm.code = code
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("name cannot be empty")
        other = (
            db.query(Permission)
            .filter(Permission.name == name, Permission.id != permission_id)
            .first()
        )
        if other:
            raise ValueError("permission name already exists")
        perm.name = name
    db.commit()
    db.refresh(perm)
    return perm


def delete_permission(db: Session, permission_id: int) -> None:
    perm = db.get(Permission, permission_id)
    if not perm:
        raise ValueError("permission not found")
    db.query(RolePermission).filter_by(permission_id=permission_id).delete()
    try:
        db.delete(perm)
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise EntityInUseError(
            "این دسترسی در بخش دیگری از سیستم استفاده شده و قابل حذف نیست",
            code="PERMISSION_IN_USE",
            permission_id=permission_id,
        ) from err


# ======================
# ASSIGN PERMISSION → ROLE
# ======================
def get_role_permissions(db: Session, role_id: int) -> list[Permission]:
    role = db.get(Role, role_id)
    if not role:
        raise ValueError("role not found")
    return (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role_id)
        .order_by(Permission.id.asc())
        .all()
    )


def replace_role_permissions(
    db: Session, role_id: int, permission_ids: list[int]
) -> list[Permission]:
    role = db.get(Role, role_id)
    if not role:
        raise ValueError("role not found")

    unique_ids = list(dict.fromkeys(permission_ids))
    if unique_ids:
        found = (
            db.query(Permission.id).filter(Permission.id.in_(unique_ids)).all()
        )
        found_ids = {row[0] for row in found}
        missing = [pid for pid in unique_ids if pid not in found_ids]
        if missing:
            raise ValueError(f"permission not found: {missing}")

    db.query(RolePermission).filter_by(role_id=role_id).delete(
        synchronize_session=False
    )
    for permission_id in unique_ids:
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))
    db.commit()
    return get_role_permissions(db, role_id)


def assign_permission_to_role(db: Session, role_id: int, permission_id: int):
    role = db.query(Role).filter_by(id=role_id).first()
    if not role:
        raise ValueError("role not found")

    permission = db.query(Permission).filter_by(id=permission_id).first()
    if not permission:
        raise ValueError("permission not found")

    exists = (
        db.query(RolePermission)
        .filter_by(role_id=role_id, permission_id=permission_id)
        .first()
    )
    if exists:
        return exists

    rp = RolePermission(role_id=role_id, permission_id=permission_id)
    db.add(rp)
    db.commit()
    db.refresh(rp)
    return rp


# ======================
# ASSIGN ROLE → USER
# ======================


def assign_role_to_user(
    db: Session, user_id: int, role_id: int, *, commit: bool = True
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError("user not found")

    role = db.query(Role).filter_by(id=role_id).first()
    if not role:
        raise ValueError("role not found")

    exists = db.query(UserRole).filter_by(user_id=user_id, role_id=role_id).first()
    if exists:
        if not exists.is_active:
            _assert_singleton_slot_available(db, role_id, for_user_id=user_id)
            exists.is_active = True
            if commit:
                db.commit()
            else:
                db.flush()
            db.refresh(exists)
        return exists

    _assert_singleton_slot_available(db, role_id, for_user_id=user_id)

    user_role = UserRole(user_id=user_id, role_id=role_id, is_active=True)
    db.add(user_role)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(user_role)
    return user_role


def unassign_permission_from_role(db: Session, role_id: int, permission_id: int) -> None:
    rp = (
        db.query(RolePermission)
        .filter_by(role_id=role_id, permission_id=permission_id)
        .first()
    )
    if not rp:
        raise ValueError("role permission assignment not found")
    db.delete(rp)
    db.commit()


def revoke_role(db: Session, user_role_id: int):
    user_role = db.query(UserRole).filter_by(id=user_role_id).first()
    if not user_role:
        raise ValueError("user_role not found")
    user_role.is_active = False
    db.commit()
    db.refresh(user_role)
    return user_role
