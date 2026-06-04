"""
Apply idempotent DB schema patches (users card/sheba, workflow, payment_request, …).

Run from project root:
  python scripts/apply_schema_patches.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect

from app.core.database import engine
from app.core.schema_patch import (
    ensure_department_schema,
    ensure_financial_schema,
    ensure_payment_request_schema,
    ensure_permissions_schema,
    ensure_roles_schema,
    ensure_postgres_sequences,
    ensure_user_profile_schema,
    ensure_workflow_schema,
    ensure_petty_cash_schema,
    ensure_financial_document_schema,
)


def main() -> None:
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    print(f"Dialect: {engine.dialect.name}")

    ensure_user_profile_schema(engine)
    ensure_department_schema(engine)
    ensure_permissions_schema(engine)
    ensure_roles_schema(engine)
    ensure_workflow_schema(engine)
    ensure_payment_request_schema(engine)
    ensure_financial_schema(engine)
    ensure_petty_cash_schema(engine)
    ensure_financial_document_schema(engine)
    ensure_postgres_sequences(engine)

    if "users" in inspect(engine).get_table_names():
        cols = sorted(c["name"] for c in inspect(engine).get_columns("users"))
        print("users columns:", ", ".join(cols))
        for name in ("card_number", "sheba_number"):
            print(f"  {name}: {'OK' if name in cols else 'MISSING'}")

    print("Done.")


if __name__ == "__main__":
    main()
