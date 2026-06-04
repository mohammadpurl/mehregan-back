from __future__ import annotations

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.orm import Session

from app.models.user import User


def _permissions_table(db: Session) -> Table:
    md = MetaData()
    return Table("permissions", md, autoload_with=db.bind)


def _role_permissions_table(db: Session) -> Table:
    md = MetaData()
    return Table("role_permissions", md, autoload_with=db.bind)


def _user_roles_table(db: Session) -> Table:
    md = MetaData()
    return Table("user_roles", md, autoload_with=db.bind)


def _roles_table(db: Session) -> Table:
    md = MetaData()
    return Table("roles", md, autoload_with=db.bind)


def permission_matches(have: set[str], need: str) -> bool:
    """بررسی دسترسی با پشتیبانی از * و wildcard مثل item.*"""
    if not need:
        return True
    if "*" in have:
        return True
    if need in have:
        return True
    for p in have:
        if p.endswith(".*"):
            prefix = p[:-2]
            if need == prefix or need.startswith(prefix + "."):
                return True
    return False


def get_user_permissions_db(db: Session, user_id: int) -> set[str]:
    """
    Schema-safe permissions fetch. Uses reflection so it works even if permissions.code
    column is missing in the database.
    """
    perms = _permissions_table(db)
    rp = _role_permissions_table(db)
    ur = _user_roles_table(db)

    perm_col = perms.c.code if "code" in perms.c else perms.c.name

    stmt = (
        select(perm_col)
        .select_from(
            ur.join(rp, rp.c.role_id == ur.c.role_id).join(
                perms, perms.c.id == rp.c.permission_id
            )
        )
        .where(ur.c.user_id == user_id)
    )
    if "is_active" in ur.c:
        stmt = stmt.where(ur.c.is_active == True)  # noqa: E712

    rows = db.execute(stmt).all()
    return {str(r[0]) for r in rows if r and r[0]}


def get_user_roles_db(db: Session, user_id: int) -> list[str]:
    roles = _roles_table(db)
    ur = _user_roles_table(db)

    stmt = (
        select(roles.c.name)
        .select_from(ur.join(roles, roles.c.id == ur.c.role_id))
        .where(ur.c.user_id == user_id)
    )
    if "is_active" in ur.c:
        stmt = stmt.where(ur.c.is_active == True)  # noqa: E712

    rows = db.execute(stmt).all()
    return [str(r[0]) for r in rows if r and r[0]]


def user_has_permission_db(db: Session, user_id: int, permission_code: str) -> bool:
    perms = get_user_permissions_db(db, user_id)
    return permission_matches(perms, permission_code)


def build_user_auth_context(db: Session, user_id: int) -> dict:
    """roles و permissions فعال کاربر — برای JWT، /auth/me و منو."""
    roles = get_user_roles_db(db, user_id)
    permissions = sorted(get_user_permissions_db(db, user_id))
    return {"roles": roles, "permissions": permissions}


def get_user_permissions(user: User):
    """
    Legacy helper kept for compatibility in existing code paths.
    Prefer get_user_permissions_db for schema-safe behavior.
    """
    permissions = set()
    for ur in user.user_roles:
        if hasattr(ur, "is_active") and not ur.is_active:
            continue
        for rp in ur.role.role_permissions:
            code = getattr(rp.permission, "code", None) or getattr(
                rp.permission, "name", None
            )
            if code:
                permissions.add(code)
    return permissions
