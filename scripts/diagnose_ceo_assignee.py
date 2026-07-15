"""
تشخیص علت خطای «هیچ کاربر فعالی با نقش مدیرعامل یافت نشد» برای کاربر مشخص.

  python scripts/diagnose_ceo_assignee.py
  python scripts/diagnose_ceo_assignee.py --username mjyounesi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole

CEO_ALIASES = ("ceo", "managing_director", "مدیرعامل")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="mjyounesi")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(func.lower(User.username) == args.username.strip().lower())
            .first()
        )
        if not user:
            print(f"FAIL: کاربر «{args.username}» یافت نشد")
            return

        print(f"User id={user.id} username={user.username} is_active={user.is_active}")

        roles = (
            db.query(Role, UserRole)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user.id)
            .all()
        )
        if not roles:
            print("FAIL: هیچ نقشی به این کاربر وصل نیست")
        for role, ur in roles:
            print(
                f"  role name={role.name!r} display={role.display_name!r} "
                f"user_role.is_active={ur.is_active}"
            )

        ceo_roles = (
            db.query(Role)
            .filter(func.lower(Role.name).in_([a.lower() for a in CEO_ALIASES]))
            .all()
        )
        print("CEO-like roles in DB:")
        for r in ceo_roles:
            holders = (
                db.query(User.username, User.is_active, UserRole.is_active)
                .join(UserRole, UserRole.user_id == User.id)
                .filter(UserRole.role_id == r.id)
                .all()
            )
            print(f"  {r.name!r} (id={r.id}) holders={holders}")

        managed = db.query(User).filter(User.manager_id == user.id).all()
        print(f"Users with this person as direct manager: {[u.username for u in managed]}")
        print(
            "NOTE: اگر درخواست‌دهنده مدیر مستقیمش همین کاربر باشد، "
            "مرحلهٔ «تأیید مدیرعامل» او را به خاطر قانون دو مرحلهٔ پشت‌سرهم حذف می‌کند."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
