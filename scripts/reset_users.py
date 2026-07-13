"""
حذف کاربران فعلی و آماده‌سازی برای درج مجدد.

  # فقط نمایش (dry-run)
  python scripts/reset_users.py

  # حذف کاربران (+ user_roles) — اگر داده کسب‌وکار به کاربر وصل باشد خطا می‌دهد
  python scripts/reset_users.py --yes

  # قبل از حذف، FKهای nullable را NULL می‌کند و ردیف‌های وابستهٔ سبک را پاک می‌کند
  python scripts/reset_users.py --yes --clear-refs

  # فقط غیرفعال کردن (حذف فیزیکی نه)
  python scripts/reset_users.py --yes --deactivate-only

  # تولید hash رمز برای SQL
  python scripts/hash_password.py "MyStrongPass"

  # فایل SQL قالب:
  #   scripts/sql/users_reset_and_insert.sql
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine


# Nullable FK columns → set NULL before deleting users
NULLABLE_USER_FK_UPDATES: list[tuple[str, str]] = [
    ("users", "manager_id"),
    ("departments", "head_user_id"),
    ("organizations", "manager_id"),
    ("inbox", "user_id"),
    ("workflow_steps", "assigned_user_id"),
    ("inventory_transactions", "created_by"),
    ("requests", "invoice_paid_by"),
    ("payment_requests", "payment_marked_by"),
    ("goods_receipts", "posted_by"),
    ("ad_hoc_task_steps", "assignee_id"),
]

# Child tables that are safe to wipe when resetting users on a fresh/staging DB
SAFE_CHILD_DELETES: list[str] = [
    "user_roles",
    "notifications",
    "inbox",
    "audit_logs",
]


def _table_exists(db: Session, table: str) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": table},
    ).first()
    return row is not None


def _column_exists(db: Session, table: str, column: str) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :t
              AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _count(db: Session, table: str) -> int:
    if not _table_exists(db, table):
        return 0
    return int(db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)


def list_user_refs(db: Session) -> list[tuple[str, str, int]]:
    """Find tables/columns referencing users.id with row counts."""
    rows = db.execute(
        text(
            """
            SELECT
              tc.table_name,
              kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND ccu.table_name = 'users'
              AND ccu.column_name = 'id'
            ORDER BY tc.table_name, kcu.column_name
            """
        )
    ).all()
    out: list[tuple[str, str, int]] = []
    for table, column in rows:
        if table == "users" and column == "id":
            continue
        n = int(
            db.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NOT NULL')
            ).scalar()
            or 0
        )
        out.append((table, column, n))
    return out


def deactivate_all_users(db: Session) -> int:
    result = db.execute(text("UPDATE users SET is_active = false"))
    return int(result.rowcount or 0)


def clear_nullable_refs(db: Session) -> None:
    for table, column in NULLABLE_USER_FK_UPDATES:
        if not _table_exists(db, table) or not _column_exists(db, table, column):
            continue
        n = db.execute(
            text(f'UPDATE "{table}" SET "{column}" = NULL WHERE "{column}" IS NOT NULL')
        ).rowcount
        print(f"  nulled {table}.{column}: {n}")


def delete_safe_children(db: Session) -> None:
    for table in SAFE_CHILD_DELETES:
        if not _table_exists(db, table):
            continue
        n = db.execute(text(f'DELETE FROM "{table}"')).rowcount
        print(f"  deleted from {table}: {n}")


def delete_all_users(db: Session) -> int:
    # Break self-FK first
    if _column_exists(db, "users", "manager_id"):
        db.execute(text("UPDATE users SET manager_id = NULL"))
    result = db.execute(text("DELETE FROM users"))
    # Reset sequence if postgres
    try:
        db.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), 1, false)"))
    except Exception:
        pass
    return int(result.rowcount or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset users table")
    parser.add_argument("--yes", action="store_true", help="Apply changes")
    parser.add_argument(
        "--deactivate-only",
        action="store_true",
        help="Only set is_active=false (no DELETE)",
    )
    parser.add_argument(
        "--clear-refs",
        action="store_true",
        help="Null nullable FKs + delete user_roles/notifications/inbox/audit_logs before DELETE",
    )
    args = parser.parse_args()

    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    db = SessionLocal()
    try:
        user_count = _count(db, "users")
        ur_count = _count(db, "user_roles")
        print(f"Current: users={user_count} user_roles={ur_count}")
        print("FK references to users.id:")
        refs = list_user_refs(db)
        for table, column, n in refs:
            mark = " " if n == 0 else "*"
            print(f"  {mark} {table}.{column} = {n} rows")

        if not args.yes:
            print("\nDry-run only. Re-run with --yes to apply.")
            print("Examples:")
            print("  python scripts/reset_users.py --yes --deactivate-only")
            print("  python scripts/reset_users.py --yes --clear-refs")
            print("SQL template: scripts/sql/users_reset_and_insert.sql")
            return

        if args.deactivate_only:
            n = deactivate_all_users(db)
            db.commit()
            print(f"\nDeactivated {n} user(s).")
            return

        if args.clear_refs:
            print("Clearing nullable refs + safe child tables ...")
            clear_nullable_refs(db)
            delete_safe_children(db)
        else:
            # Always remove user_roles so DELETE users can succeed when no other data
            if _table_exists(db, "user_roles"):
                n = db.execute(text("DELETE FROM user_roles")).rowcount
                print(f"  deleted from user_roles: {n}")

        print("Deleting users ...")
        try:
            n = delete_all_users(db)
            db.commit()
            print(f"\nDeleted {n} user(s). Sequence reset.")
            print("Next: edit scripts/sql/users_reset_and_insert.sql and run it,")
            print("  or use: python scripts/hash_password.py 'YourPassword'")
        except Exception as exc:
            db.rollback()
            print("\nDELETE failed (FK still referencing users).")
            print(f"  {exc}")
            print("Re-run with: python scripts/reset_users.py --yes --clear-refs")
            print("If business tables still block, delete/archive those rows first.")
            raise SystemExit(1) from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
