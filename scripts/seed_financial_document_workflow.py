"""
گردش‌کار اسناد مالی: مدیرعامل → تأیید نهایی مدیر مالی

  python scripts/seed_financial_document_workflow.py
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
        "label": "تأیید مدیرعامل",
        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
        "assignee_strategy": "role_pool",
        "step_action": "approval",
    },
    {
        "order": 2,
        "label": "تأیید نهایی — مدیر مالی",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
        "step_action": "final_approval",
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        upsert_definition(
            db,
            ref_type="financial_document",
            name="اسناد مالی",
            steps=STEPS,
        )
        db.commit()
        print("OK: workflow_definitions.financial_document")
    finally:
        db.close()


if __name__ == "__main__":
    main()
