"""
Assign a role to a user (creates or reactivates user_roles link).

  python scripts/grant_role_to_user.py --username mjyounesi --role super-admin
  python scripts/grant_role_to_user.py --user-id 3 --role super-admin
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


def grant_role_to_user(*, user_id: int | None, username: str | None, role_name: str) -> None:
    db = SessionLocal()
    try:
        if user_id is not None:
            user = db.get(User, user_id)
            if not user:
                raise SystemExit(f"user id={user_id} not found")
        elif username:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise SystemExit(f"user username={username!r} not found")
        else:
            raise SystemExit("pass --user-id or --username")

        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            raise SystemExit(f"role {role_name!r} not found")

        link = (
            db.query(UserRole)
            .filter_by(user_id=user.id, role_id=role.id)
            .first()
        )
        if link:
            link.is_active = True
            print(
                f"reactivated role {role_name!r} for "
                f"user_id={user.id} username={user.username}"
            )
        else:
            db.add(UserRole(user_id=user.id, role_id=role.id, is_active=True))
            print(
                f"granted role {role_name!r} to "
                f"user_id={user.id} username={user.username}"
            )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant a role to a user")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--user-id", type=int, metavar="ID")
    target.add_argument("--username", metavar="NAME")
    parser.add_argument("--role", default="super-admin", help="Role name (default: super-admin)")
    args = parser.parse_args()
    grant_role_to_user(
        user_id=args.user_id,
        username=args.username,
        role_name=args.role,
    )


if __name__ == "__main__":
    main()
