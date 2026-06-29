"""
Seed roles + permissions on empty DB (non-destructive).

Use when reset_rbac.py --yes fails or DB is fresh.

  docker compose exec -T backend python scripts/seed_rbac_if_empty.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal, engine
from app.core.schema_patch import ensure_permissions_schema, ensure_roles_schema
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission

_reset_spec = importlib.util.spec_from_file_location(
    "reset_rbac_module", ROOT / "scripts" / "reset_rbac.py"
)
_reset = importlib.util.module_from_spec(_reset_spec)
assert _reset_spec.loader is not None
_reset_spec.loader.exec_module(_reset)

PERMISSIONS = _reset.PERMISSIONS
ROLES = _reset.ROLES
ROLE_PERMISSIONS = _reset.ROLE_PERMISSIONS
_expand_role_permissions = _reset._expand_role_permissions


def main() -> None:
    ensure_permissions_schema(engine)
    ensure_roles_schema(engine)

    db = SessionLocal()
    try:
        role_count = db.query(Role).filter(~Role.name.like("__deprecated_%")).count()
        if role_count > 0:
            print(f"Roles already exist ({role_count}). Skipping seed_rbac_if_empty.")
            return

        perm_by_code: dict[str, int] = {}
        for code, label in PERMISSIONS:
            existing = db.execute(
                select(Permission).where(Permission.code == code)
            ).scalar_one_or_none()
            if existing:
                perm_by_code[code] = existing.id
                continue
            row = Permission(name=label, code=code)
            db.add(row)
            db.flush()
            perm_by_code[code] = row.id

        role_by_name: dict[str, int] = {}
        for name, label in ROLES:
            existing = db.execute(
                select(Role).where(Role.name == name)
            ).scalar_one_or_none()
            if existing:
                existing.display_name = label
                role_by_name[name] = existing.id
                continue
            row = Role(name=name, display_name=label)
            db.add(row)
            db.flush()
            role_by_name[name] = row.id

        links = 0
        for role_name, codes in ROLE_PERMISSIONS.items():
            role_id = role_by_name.get(role_name)
            if not role_id:
                continue
            for code in _expand_role_permissions(codes):
                perm_id = perm_by_code.get(code)
                if not perm_id:
                    continue
                exists = db.execute(
                    select(RolePermission.id).where(
                        RolePermission.role_id == role_id,
                        RolePermission.permission_id == perm_id,
                    )
                ).first()
                if exists:
                    continue
                db.add(RolePermission(role_id=role_id, permission_id=perm_id))
                links += 1

        db.commit()
        print(
            f"seed_rbac_if_empty done | permissions={len(perm_by_code)} "
            f"roles={len(role_by_name)} links_added={links}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
