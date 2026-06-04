"""
تعریف workflow تنخواه: مدیر مالی → مدیرعامل

  python scripts/seed_petty_cash_workflow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.services.workflow_definition_service import upsert_definition

STEPS = [
    {
        "order": 1,
        "label": "تأیید مدیر مالی",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
    },
    {
        "order": 2,
        "label": "تأیید مدیرعامل",
        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
        "assignee_strategy": "role_pool",
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        upsert_definition(
            db,
            ref_type="petty_cash",
            name="درخواست تنخواه",
            steps=STEPS,
        )
        print("OK: workflow_definitions.petty_cash")
    finally:
        db.close()


if __name__ == "__main__":
    main()
