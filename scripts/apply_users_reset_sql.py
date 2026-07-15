"""
حذف همه کاربران و درج مجدد مطابق scripts/sql/users_reset_and_insert.sql

  python scripts/apply_users_reset_sql.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.database import SessionLocal, engine

SQL_PATH = ROOT / "scripts" / "sql" / "users_reset_and_insert.sql"

# جدول‌هایی که به users وصل‌اند و جلوی DELETE را می‌گیرند (فرزند → والد)
BLOCKING_DELETES: tuple[str, ...] = (
    "ad_hoc_task_steps",
    "ad_hoc_tasks",
    "goods_receipt_lines",
    "goods_receipts",
    "purchase_order_items",
    "purchase_orders",
    "procurement_proformas",
    "request_items",
    "requests",
    "petty_cash_expense_lines",
    "petty_cash_requests",
    "mission_requests",
    "financial_documents",
    "payment_requests",
    "warehouse_forms",
    "workflow_forms",
    "workflow_approvals",
    "workflow_steps",
    "sla_records",
    "slas",
    "inbox_items",
    "notifications",
    "attachments",
    "workflow_instances",
    "audit_logs",
    "user_roles",
)

ENSURE_ROLES: list[tuple[str, str]] = [
    ("managing_director", "مدیرعامل / قائم‌مقام"),
    ("requester", "درخواست‌کننده"),
    ("procurement_officer", "مسئول خرید"),
]

COPY_PERMS: list[tuple[str, str]] = [
    ("ceo", "managing_director"),
    ("employee", "requester"),
    ("purchase_manager", "procurement_officer"),
]


def _table_exists(db, table: str) -> bool:
    return bool(
        db.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": table},
        ).first()
    )


def clear_blocking_data(db) -> None:
    for table in BLOCKING_DELETES:
        if not _table_exists(db, table):
            continue
        n = db.execute(text(f'DELETE FROM "{table}"')).rowcount
        print(f"  deleted {table}: {n}")

    if _table_exists(db, "departments"):
        db.execute(text("UPDATE departments SET head_user_id = NULL WHERE head_user_id IS NOT NULL"))
    if _table_exists(db, "users"):
        db.execute(text("UPDATE users SET manager_id = NULL"))


def ensure_roles(db) -> None:
    for name, display in ENSURE_ROLES:
        if db.execute(text("SELECT id FROM roles WHERE name = :n"), {"n": name}).first():
            continue
        db.execute(
            text(
                "INSERT INTO roles (name, display_name, is_singleton) VALUES (:n, :d, false)"
            ),
            {"n": name, "d": display},
        )
        print(f"  created role: {name}")

    for src, dst in COPY_PERMS:
        src_id = db.execute(text("SELECT id FROM roles WHERE name = :n"), {"n": src}).scalar()
        dst_id = db.execute(text("SELECT id FROM roles WHERE name = :n"), {"n": dst}).scalar()
        if not src_id or not dst_id:
            print(f"  skip perm copy {src}->{dst} (missing role)")
            continue
        n = int(
            db.execute(
                text("SELECT COUNT(*) FROM role_permissions WHERE role_id = :r"),
                {"r": dst_id},
            ).scalar()
            or 0
        )
        if n > 0:
            continue
        inserted = db.execute(
            text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :dst, permission_id FROM role_permissions WHERE role_id = :src
                """
            ),
            {"dst": dst_id, "src": src_id},
        ).rowcount
        print(f"  copied permissions {src} → {dst}: {inserted}")


def apply_sql_file(db) -> None:
    raw = SQL_PATH.read_text(encoding="utf-8")
    # حذف BEGIN/COMMIT؛ تراکنش با Session مدیریت می‌شود
    raw = re.sub(r"(?im)^\s*BEGIN\s*;\s*$", "", raw)
    raw = re.sub(r"(?im)^\s*COMMIT\s*;\s*$", "", raw)
    # اجرای کل اسکریپت (چند statement)
    db.connection().exec_driver_sql(raw)


def main() -> None:
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    db = SessionLocal()
    try:
        print("1) Clearing data that references users ...")
        clear_blocking_data(db)

        print("2) Deleting all users ...")
        n = db.execute(text("DELETE FROM users")).rowcount
        try:
            db.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), 1, false)"))
        except Exception:
            pass
        print(f"  deleted users: {n}")

        print("3) Ensuring roles required by SQL ...")
        ensure_roles(db)
        db.commit()

        print(f"4) Applying {SQL_PATH.name} ...")
        # session جدید بعد از commit برای اجرای SQL چندبخشی
        apply_sql_file(db)
        db.commit()

        rows = db.execute(
            text(
                """
                SELECT u.id, u.username,
                       COALESCE(u.first_name,'') AS first_name,
                       COALESCE(u.last_name,'') AS last_name,
                       COALESCE(string_agg(r.name, ', ' ORDER BY r.name), '') AS roles
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.is_active = true
                LEFT JOIN roles r ON r.id = ur.role_id
                GROUP BY u.id
                ORDER BY u.id
                """
            )
        ).all()
        print("\nUsers / roles:")
        for row in rows:
            print(
                f"  #{row.id:<3} {row.username:<12} "
                f"{row.first_name} {row.last_name}  →  {row.roles or '(no role)'}"
            )
        missing = [r.username for r in rows if not r.roles]
        if missing:
            print(f"\nWARNING: users without role: {', '.join(missing)}")
        print(f"\nDone. total_users={len(rows)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
