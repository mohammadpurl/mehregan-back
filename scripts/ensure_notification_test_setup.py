"""
تنظیم تست اعلان‌ها: مدیر مستقیم، نقش‌ها، workflow درخواست مالی.

  python scripts/ensure_notification_test_setup.py --list-users
  python scripts/ensure_notification_test_setup.py --yes --submitter leila --manager mardi
  python scripts/ensure_notification_test_setup.py --yes --submitter leila --manager mardi --finance-user <username>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func

from app.core.database import SessionLocal
from app.core.schema_patch import ensure_roles_schema
from app.core.database import engine
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services.org import get_user_manager
from app.services.workflow_definition_service import get_steps_config
from app.services.workflow_step_config import resolve_step_assignee_user, resolve_role_id_for_step


def _find_user(db, username: str) -> User | None:
    key = username.strip().lower()
    return (
        db.query(User)
        .filter(func.lower(User.username) == key)
        .first()
    )


def list_users(db) -> None:
    rows = db.query(User).order_by(User.id).all()
    print(f"{'id':>4}  {'username':20}  {'name':30}  manager_id")
    for u in rows:
        name = " ".join(filter(None, [u.first_name, u.last_name])).strip() or "—"
        print(f"{u.id:4}  {u.username:20}  {name:30}  {u.manager_id}")


def _ensure_role(db, user_id: int, role_name: str) -> None:
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        print(f"  WARN: role {role_name!r} missing — run scripts/reset_rbac.py --yes")
        return
    exists = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.is_active == True,  # noqa: E712
        )
        .first()
    )
    if exists:
        print(f"  OK: user {user_id} already has {role_name}")
        return
    db.add(UserRole(user_id=user_id, role_id=role.id, is_active=True))
    print(f"  granted {role_name} -> user_id={user_id}")


def preview_assignees(db, submitter_id: int) -> None:
    steps = get_steps_config(db, "payment_request")
    print(f"\nپیش‌نمایش مسیر تأیید برای submitter_id={submitter_id}:")
    assigned: list[int] = []
    for step in steps:
        role_id = resolve_role_id_for_step(db, step)
        user = resolve_step_assignee_user(
            db,
            step,
            role_id=role_id,
            submitter_id=submitter_id,
            exclude_user_ids=assigned,
        )
        label = step.get("label") or step.get("order")
        if user:
            assigned.append(user.id)
            print(f"  مرحله {step.get('order')} ({label}): user_id={user.id} username={user.username}")
        else:
            print(f"  مرحله {step.get('order')} ({label}): ❌ بدون مسئول")


def run_setup(
    *,
    submitter: str,
    manager: str,
    finance_user: str | None,
    dry_run: bool,
) -> int:
    ensure_roles_schema(engine)
    db = SessionLocal()
    try:
        sub = _find_user(db, submitter)
        mgr = _find_user(db, manager)
        if not sub:
            print(f"کاربر submitter یافت نشد: {submitter!r}")
            return 1
        if not mgr:
            print(f"کاربر manager یافت نشد: {manager!r}")
            return 1

        print(f"submitter: id={sub.id} username={sub.username}")
        print(f"manager:   id={mgr.id} username={mgr.username}")

        if sub.manager_id != mgr.id:
            print(f"  set manager_id: {sub.manager_id} -> {mgr.id}")
            if not dry_run:
                sub.manager_id = mgr.id

        finance_uid: int | None = None
        if finance_user:
            fin = _find_user(db, finance_user)
            if not fin:
                print(f"کاربر finance یافت نشد: {finance_user!r}")
                return 1
            finance_uid = fin.id
        else:
            fin_role = db.query(Role).filter(Role.name == "finance_manager").first()
            if fin_role:
                ur = (
                    db.query(UserRole)
                    .filter(
                        UserRole.role_id == fin_role.id,
                        UserRole.is_active == True,  # noqa: E712
                    )
                    .first()
                )
                if ur:
                    finance_uid = ur.user_id

        if not dry_run:
            _ensure_role(db, mgr.id, "manager")
            if finance_uid:
                _ensure_role(db, finance_uid, "finance_manager")
            elif finance_user is None:
                print("  WARN: finance_manager not set — pass --finance-user <username>")
            db.commit()

        resolved = get_user_manager(db, sub.id)
        print(f"  get_user_manager -> id={resolved.id if resolved else None} username={resolved.username if resolved else '—'}")

        preview_assignees(db, sub.id)

        if not dry_run:
            db.commit()
            cmd = [sys.executable, str(ROOT / "scripts" / "ensure_payment_workflow_setup.py")]
            if finance_uid:
                cmd.extend(["--finance-user-id", str(finance_uid)])
            subprocess.run(cmd, check=False)
    finally:
        db.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-users", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submitter", default="leila")
    parser.add_argument("--manager", default="mardi")
    parser.add_argument("--finance-user", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.list_users:
            list_users(db)
            return
    finally:
        db.close()

    dry_run = not args.yes
    if dry_run:
        print("DRY RUN (برای اعمال: --yes)\n")
    raise SystemExit(
        run_setup(
            submitter=args.submitter,
            manager=args.manager,
            finance_user=args.finance_user,
            dry_run=dry_run,
        )
    )


if __name__ == "__main__":
    main()
