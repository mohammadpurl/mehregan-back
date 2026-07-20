"""
ایجاد/بازیابی کاربر مدیرعامل — محمدجلال یونسی

  python scripts/seed_ceo_user.py
  python scripts/seed_ceo_user.py --password "رمز-جدید"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services import rbac

CEO_USERNAME = "mjyounesi"
CEO_FIRST_NAME = "محمدجلال"
CEO_LAST_NAME = "یونسی"


def seed_ceo_user(*, password: str) -> User:
    db = SessionLocal()
    try:
        ceo_role = db.query(Role).filter(Role.name == "ceo").first()
        if not ceo_role:
            raise RuntimeError("نقش ceo در دیتابیس یافت نشد. ابتدا seed RBAC را اجرا کنید.")

        user = db.query(User).filter(User.username == CEO_USERNAME).first()
        if not user:
            user = User(
                username=CEO_USERNAME,
                first_name=CEO_FIRST_NAME,
                last_name=CEO_LAST_NAME,
                hashed_password=get_password_hash(password),
                is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"Created user: {user.username} (id pending)")
        else:
            user.first_name = CEO_FIRST_NAME
            user.last_name = CEO_LAST_NAME
            user.is_active = True
            user.hashed_password = get_password_hash(password)
            print(f"Updated user: {user.username}")

        existing_link = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.role_id == ceo_role.id)
            .first()
        )
        if existing_link:
            existing_link.is_active = True
        else:
            rbac.assign_role_to_user(db, user.id, ceo_role.id, commit=False)

        db.commit()
        db.refresh(user)
        return user
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed CEO user (محمدجلال یونسی)")
    parser.add_argument(
        "--password",
        required=True,
        help="رمز عبور قوی (اجباری؛ پیش‌فرض ضعیف حذف شده است)",
    )
    args = parser.parse_args()
    if not args.password or len(args.password) < 8 or args.password in {"123456", "password", "admin"}:
        print("ERROR: رمز عبور باید حداقل ۸ کاراکتر و غیرپیش‌فرض باشد", file=sys.stderr)
        sys.exit(1)
    user = seed_ceo_user(password=args.password)
    print(f"Role: ceo — user id={user.id}, username={user.username}")


if __name__ == "__main__":
    main()
