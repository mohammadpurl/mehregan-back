"""
گردش‌کار اسناد مالی — روال یکسان مالی + سپیدار

  python scripts/seed_financial_document_workflow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.financial_workflow import UNIFIED_FINANCIAL_STEPS
from app.core.database import SessionLocal
from app.services.workflow_definition_service import upsert_definition

STEPS = list(UNIFIED_FINANCIAL_STEPS)


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
