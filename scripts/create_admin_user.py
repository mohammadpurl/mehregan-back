"""
Create or update an admin user (no HTTP /auth/register).

Usage (from Backend2/):
  python scripts/create_admin_user.py --username admin --password "StrongPass123"
  python scripts/create_admin_user.py --username admin --password "StrongPass123" --mobile 09120000000
  python scripts/create_admin_user.py --username admin --password "StrongPass123" --role super-admin

Requires RBAC roles to exist (run seed/reset_rbac first if needed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


DEFAULT_ROLE = "super-admin"


def create_or_update_admin(
    *,
    username: str,
    password: str,
    role_name: str = DEFAULT_ROLE,
    mobile: str | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            raise RuntimeError(
                f"Role '{role_name}' not found. Seed RBAC first "
                "(e.g. python scripts/reset_rbac.py --yes)."
            )

        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                hashed_password=get_password_hash(password),
                mobile=mobile,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"Created user username={username} id={user.id}")
        else:
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            if mobile is not None:
                user.mobile = mobile
            if email is not None:
                user.email = email
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            print(f"Updated user username={username} id={user.id}")

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
        db.refresh(user)
        print(f"Granted role '{role_name}' to username={username}")
        return user
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create/update an admin user via CLI (no HTTP register)"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default=DEFAULT_ROLE, help=f"Role name (default: {DEFAULT_ROLE})")
    parser.add_argument("--mobile", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--first-name", default=None)
    parser.add_argument("--last-name", default=None)
    args = parser.parse_args()

    try:
        create_or_update_admin(
            username=args.username.strip(),
            password=args.password,
            role_name=args.role.strip(),
            mobile=args.mobile,
            email=args.email,
            first_name=args.first_name,
            last_name=args.last_name,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
