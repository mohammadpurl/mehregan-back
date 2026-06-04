"""
Seed ERP roles + permissions + role-permission links.

Run:
  python -m app.scripts.seed_erp_authorization

This script is designed to work even if the `permissions` table does NOT yet have
the `code` column (older schema). In that case it uses `Permission.name` as the identifier.
"""

from __future__ import annotations

from sqlalchemy import MetaData, Table, inspect, select, insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.models.role import Role


ROLES: list[str] = [
    "super-admin",
    "admin",
    "ceo",
    "finance_manager",
    "accountant",
    "purchase_manager",
    "purchase_officer",
    "warehouse_manager",
    "warehouse",
    "manager",
    "project_manager",
    "employee",
]

# Coarse-grained permissions (stable “capabilities”)
PERMISSIONS: list[str] = [
    "dashboard.read",
    "workflow.read",
    "workflow.inbox.read",
    "workflow.tracking.read",
    "workflow.all.read",
    "workflow.approve",
    "workflow.correction",
    "procurement.read",
    "procurement.write",
    "inventory.read",
    "masterdata.manage",
    "admin.manage",
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super-admin": ["*"],
    "admin": ["admin.manage", "masterdata.manage", "procurement.write", "procurement.read", "inventory.read", "workflow.approve", "workflow.all.read", "workflow.tracking.read", "workflow.inbox.read", "workflow.read", "dashboard.read"],
    "ceo": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.all.read",
        "workflow.tracking.read",
        "workflow.approve",
    ],
    "finance_manager": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "workflow.approve", "procurement.read", "inventory.read"],
    "accountant": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "procurement.read"],
    "purchase_manager": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "workflow.approve", "procurement.read", "procurement.write"],
    "purchase_officer": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "procurement.read", "procurement.write"],
    "warehouse_manager": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "workflow.approve", "inventory.read"],
    "warehouse": ["dashboard.read", "inventory.read"],
    "manager": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "workflow.approve"],
    "project_manager": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read", "workflow.approve"],
    "employee": ["dashboard.read", "workflow.read", "workflow.inbox.read", "workflow.tracking.read"],
    "workflow_corrector": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.all.read",
        "workflow.approve",
        "workflow.correction",
    ],
}


def _permissions_has_code_column(db) -> bool:
    insp = inspect(db.bind)
    cols = {c["name"] for c in insp.get_columns("permissions")}
    return "code" in cols


def _get_or_create_role(db, name: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name)
    db.add(role)
    db.flush()
    return role


def _permissions_table(db) -> Table:
    md = MetaData()
    return Table("permissions", md, autoload_with=db.bind)


def _role_permissions_table(db) -> Table:
    md = MetaData()
    return Table("role_permissions", md, autoload_with=db.bind)


def _get_or_create_permission_id(db, code_or_name: str, has_code: bool) -> int:
    perms = _permissions_table(db)

    if has_code and "code" in perms.c:
        stmt = select(perms.c.id).where(perms.c.code == code_or_name).limit(1)
        row = db.execute(stmt).first()
        if row:
            return int(row[0])
        res = db.execute(insert(perms).values(name=code_or_name, code=code_or_name).returning(perms.c.id))
        return int(res.scalar_one())

    # older schema: use name only
    stmt = select(perms.c.id).where(perms.c.name == code_or_name).limit(1)
    row = db.execute(stmt).first()
    if row:
        return int(row[0])
    res = db.execute(insert(perms).values(name=code_or_name).returning(perms.c.id))
    return int(res.scalar_one())


def _ensure_role_permission(db, role_id: int, permission_id: int) -> None:
    rp = _role_permissions_table(db)
    stmt = (
        select(rp.c.id)
        .where(rp.c.role_id == role_id, rp.c.permission_id == permission_id)
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row:
        return
    db.execute(insert(rp).values(role_id=role_id, permission_id=permission_id))


def main() -> None:
    db = SessionLocal()
    try:
        has_code = _permissions_has_code_column(db)

        created_roles = 0
        created_permissions = 0
        created_links = 0

        # roles
        for r in ROLES:
            before = db.query(Role).filter(Role.name == r).first()
            _get_or_create_role(db, r)
            if before is None:
                created_roles += 1

        # permissions
        for p in PERMISSIONS:
            perms = _permissions_table(db)
            if has_code and "code" in perms.c:
                before = db.execute(select(perms.c.id).where(perms.c.code == p).limit(1)).first()
            else:
                before = db.execute(select(perms.c.id).where(perms.c.name == p).limit(1)).first()
            _get_or_create_permission_id(db, p, has_code)
            if before is None:
                created_permissions += 1

        # links
        for role_name, perm_list in ROLE_PERMISSIONS.items():
            role = _get_or_create_role(db, role_name)

            if "*" in perm_list:
                # grant all known coarse permissions
                expanded = PERMISSIONS
            else:
                expanded = perm_list

            for perm_code in expanded:
                perm_id = _get_or_create_permission_id(db, perm_code, has_code)
                rp = _role_permissions_table(db)
                before = db.execute(
                    select(rp.c.id)
                    .where(rp.c.role_id == role.id, rp.c.permission_id == perm_id)
                    .limit(1)
                ).first()
                _ensure_role_permission(db, role.id, perm_id)
                if before is None:
                    created_links += 1

        db.commit()
        print(
            f"Seed completed | roles_added={created_roles} permissions_added={created_permissions} links_added={created_links} has_permissions_code={has_code}"
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

