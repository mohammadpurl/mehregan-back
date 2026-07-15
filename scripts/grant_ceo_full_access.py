"""
به نقش ceo همهٔ دسترسی‌ها را می‌دهد
و (اختیاری) نقش super-admin را به کاربر مدیرعامل می‌دهد.

  python scripts/grant_ceo_full_access.py
  python scripts/grant_ceo_full_access.py --username mjyounesi
  python scripts/grant_ceo_full_access.py --skip-super-admin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services import rbac


def _perm_code(p: Permission) -> str:
    return (p.code or p.name or "").strip()


def grant_all_permissions_to_role(db: Session, role_name: str = "ceo") -> list[str]:
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise SystemExit(f"نقش {role_name!r} یافت نشد. ابتدا seed RBAC را اجرا کنید.")

    permissions = db.query(Permission).order_by(Permission.id.asc()).all()
    if not permissions:
        raise SystemExit("هیچ permission ای در دیتابیس نیست.")

    codes = [_perm_code(p) for p in permissions if _perm_code(p)]
    rbac.replace_role_permissions(db, role.id, [p.id for p in permissions])
    return codes


def grant_role_to_username(
    db: Session, *, username: str, role_name: str = "super-admin"
) -> None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise SystemExit(f"کاربر {username!r} یافت نشد.")

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise SystemExit(f"نقش {role_name!r} یافت نشد.")

    link = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
        .first()
    )
    if link:
        link.is_active = True
        db.commit()
        print(
            f"reactivated role {role_name!r} for "
            f"user_id={user.id} username={user.username}"
        )
        return

    db.add(UserRole(user_id=user.id, role_id=role.id, is_active=True))
    db.commit()
    print(
        f"granted role {role_name!r} to "
        f"user_id={user.id} username={user.username}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grant all permissions to ceo (+ optional super-admin to user)"
    )
    parser.add_argument(
        "--username",
        default="mjyounesi",
        help="User to receive super-admin (default: mjyounesi)",
    )
    parser.add_argument(
        "--skip-super-admin",
        action="store_true",
        help="Only update ceo permissions; do not grant super-admin",
    )
    parser.add_argument(
        "--role",
        default="ceo",
        help="Role to receive all permissions (default: ceo)",
    )
    args = parser.parse_args()

    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    db = SessionLocal()
    try:
        codes = grant_all_permissions_to_role(db, args.role)
        print(f"OK: role {args.role!r} now has {len(codes)} permission(s)")
        if "*" in codes:
            print("  includes wildcard permission: *")
        else:
            print("  sample:", ", ".join(codes[:8]), ("..." if len(codes) > 8 else ""))

        if not args.skip_super_admin:
            grant_role_to_username(
                db, username=args.username, role_name="super-admin"
            )
            print(
                f"Note: re-login required for user {args.username!r} "
                "so the JWT picks up the new roles/permissions."
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
