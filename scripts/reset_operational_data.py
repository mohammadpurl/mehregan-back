"""
پاک‌سازی دادهٔ عملیاتی برای تست مجدد کل سیستم.

**نگه‌داشته می‌شود:**
  users, roles, permissions, role_permissions, user_roles, workflow_definitions

**حذف می‌شود:**
  همه درخواست‌ها، workflow runtime، inbox، انبار، تدارکات، master data،
  departments، audit، SLA runtime، assignment_rules و ...

اجرا:
  python scripts/reset_operational_data.py              # dry-run
  python scripts/reset_operational_data.py --yes         # اجرای واقعی
  python scripts/reset_operational_data.py --yes --purge-uploads
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.core.config import UPLOAD_DIRECTORY
from app.core.database import SessionLocal, engine
from app.core.schema_patch import ensure_postgres_sequences
from app.services.attachment_service import ENTITY_UPLOAD_DIRS

# جداولی که دست‌نخورده می‌مانند
PRESERVED_TABLES: frozenset[str] = frozenset(
    {
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "workflow_definitions",
    }
)

# ترتیب حذف (فرزند قبل از والد) — برای SQLite یا fallback
DELETE_ORDER: tuple[str, ...] = (
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
    "inventory_transactions",
    "stocks",
    "items",
    "categories",
    "warehouses",
    "suppliers",
    "counterparty_bank_accounts",
    "counterparties",
    "company_bank_accounts",
    "audit_logs",
    "sla_policies",
    "assignment_rules",
    "payments",
)

# جداولی که نباید در TRUNCATE ... CASCADE باشند (وگرنه users/user_roles هم پاک می‌شوند)
TRUNCATE_EXCLUDED: frozenset[str] = frozenset({"departments"})


def _existing_tables() -> set[str]:
    insp = inspect(engine)
    return set(insp.get_table_names())


def _tables_to_clear(existing: set[str]) -> list[str]:
    ordered = [t for t in DELETE_ORDER if t in existing and t not in PRESERVED_TABLES]
    # هر جدول دیگری در DB که در لیست preserve نیست (به‌جز alembic)
    extras = sorted(
        t
        for t in existing
        if t not in PRESERVED_TABLES
        and t not in ordered
        and not t.startswith("alembic")
    )
    return ordered + extras


def _count_rows(db, table: str) -> int:
    return db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0


def _null_user_departments(db) -> None:
    if "users" not in _existing_tables():
        return
    db.execute(text("UPDATE users SET department_id = NULL"))


def _null_department_tree(db) -> None:
    if "departments" not in _existing_tables():
        return
    db.execute(text("UPDATE departments SET parent_id = NULL"))
    db.execute(text("UPDATE departments SET head_user_id = NULL"))


def _truncate_postgres(db, tables: list[str]) -> None:
    cascade_tables = [t for t in tables if t not in TRUNCATE_EXCLUDED]
    if cascade_tables:
        quoted = ", ".join(f'"{t}"' for t in cascade_tables)
        db.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))

    for table in (t for t in tables if t in TRUNCATE_EXCLUDED):
        db.execute(text(f'DELETE FROM "{table}"'))


def _delete_fallback(db, tables: list[str]) -> None:
    for table in tables:
        db.execute(text(f'DELETE FROM "{table}"'))


def _purge_upload_dirs(*, dry_run: bool) -> list[str]:
    cleared: list[str] = []
    base = UPLOAD_DIRECTORY.resolve()
    if not base.is_dir():
        return cleared
    for folder_name in ENTITY_UPLOAD_DIRS.values():
        path = base / folder_name
        if not path.is_dir():
            continue
        cleared.append(str(path))
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True, exist_ok=True)
    return cleared


def reset_operational_data(
    *,
    dry_run: bool,
    purge_uploads: bool,
) -> dict[str, int | list[str]]:
    existing = _existing_tables()
    tables = _tables_to_clear(existing)
    stats: dict[str, int | list[str]] = {"tables": len(tables), "rows_before": 0}
    row_counts: dict[str, int] = {}

    db = SessionLocal()
    try:
        for table in tables:
            row_counts[table] = _count_rows(db, table)
        stats["rows_before"] = sum(row_counts.values())
        stats["row_counts"] = row_counts  # type: ignore[assignment]

        print("Tables to clear (preserved: users, roles, permissions, role_permissions, user_roles, workflow_definitions):")
        for table in tables:
            print(f"  - {table}: {row_counts.get(table, 0)} rows")

        preserved_counts = {
            t: _count_rows(db, t) for t in sorted(PRESERVED_TABLES) if t in existing
        }
        print("\nPreserved row counts:")
        for t, c in preserved_counts.items():
            print(f"  - {t}: {c}")

        if dry_run:
            db.rollback()
            print("\nDRY RUN — no changes committed.")
            if purge_uploads:
                dirs = _purge_upload_dirs(dry_run=True)
                if dirs:
                    print("Would purge upload folders:")
                    for d in dirs:
                        print(f"  - {d}")
            return stats

        _null_user_departments(db)
        _null_department_tree(db)

        if engine.dialect.name == "postgresql":
            _truncate_postgres(db, tables)
        else:
            _delete_fallback(db, tables)

        for preserved in sorted(PRESERVED_TABLES):
            if preserved in existing and _count_rows(db, preserved) == 0:
                raise RuntimeError(
                    f"جدول محافظت‌شده «{preserved}» خالی شد — reset متوقف شد. "
                    "لطفاً از backup بازیابی کنید."
                )

        db.commit()
        ensure_postgres_sequences(engine)

        if purge_uploads:
            stats["purged_upload_dirs"] = _purge_upload_dirs(dry_run=False)  # type: ignore[assignment]

        print("\nCommitted — operational data cleared.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clear operational DB data for full system retest (keeps users/RBAC/workflow definitions)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="اجرای واقعی (بدون این فقط dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="فقط نمایش آمار (پیش‌فرض اگر --yes نباشد)",
    )
    parser.add_argument(
        "--purge-uploads",
        action="store_true",
        help="پاک کردن پوشه‌های پیوست (uploads) — عکس پروفایل دست نخورده می‌ماند",
    )
    args = parser.parse_args()

    dry_run = args.dry_run or not args.yes
    if not args.yes and not args.dry_run:
        print("WARNING: dry-run mode. Use --yes to apply changes.\n")

    if args.yes and not args.dry_run:
        confirm = input(
            "همه داده‌های عملیاتی حذف می‌شوند (users/RBAC/workflow_definitions می‌مانند). ادامه؟ [y/N]: "
        )
        if confirm.strip().lower() not in ("y", "yes", "بله"):
            print("Cancelled.")
            return

    stats = reset_operational_data(dry_run=dry_run, purge_uploads=args.purge_uploads)
    print(f"\nTotal rows cleared (before): {stats.get('rows_before', 0)}")


if __name__ == "__main__":
    main()
