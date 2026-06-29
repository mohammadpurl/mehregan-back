"""Grant super-admin role to a user by id."""

from __future__ import annotations

import argparse
import sys

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant super-admin role to a user")
    parser.add_argument("user_id", type=int, help="User id")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.get(User, args.user_id)
        role = db.query(Role).filter(Role.name == "super-admin").first()
        if not user or not role:
            print("user or super-admin role not found", file=sys.stderr)
            raise SystemExit(1)

        link = (
            db.query(UserRole)
            .filter_by(user_id=user.id, role_id=role.id)
            .first()
        )
        if link:
            link.is_active = True
        else:
            db.add(UserRole(user_id=user.id, role_id=role.id, is_active=True))

        db.commit()
        print(
            f"granted super-admin to user_id={user.id} username={user.username}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
