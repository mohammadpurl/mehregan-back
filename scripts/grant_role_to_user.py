"""
Assign a role to a user (creates or reactivates user_roles link).

  python scripts/grant_role_to_user.py --user-id 1 --role super-admin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


def grant_role_to_user(*, user_id: int, role_name: str) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        role = db.query(Role).filter(Role.name == role_name).first()
        if not user:
            raise SystemExit(f"user id={user_id} not found")
        if not role:
            raise SystemExit(f"role {role_name!r} not found")

        link = (
            db.query(UserRole)
            .filter_by(user_id=user.id, role_id=role.id)
            .first()
        )
        if link:
            link.is_active = True
            print(f"reactivated role {role_name!r} for user_id={user.id} username={user.username}")
        else:
            db.add(UserRole(user_id=user.id, role_id=role.id, is_active=True))
            print(f"granted role {role_name!r} to user_id={user.id} username={user.username}")

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant a role to a user")
    parser.add_argument("--user-id", type=int, required=True, metavar="ID")
    parser.add_argument("--role", default="super-admin", help="Role name (default: super-admin)")
    args = parser.parse_args()
    grant_role_to_user(user_id=args.user_id, role_name=args.role)


if __name__ == "__main__":
    main()
