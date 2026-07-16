"""
گردش‌کار تأیید خرج تنخواه: مدیر مستقیم → مدیر مالی → مدیرعامل

  python scripts/seed_petty_cash_settlement_workflow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.petty_cash import (
    PETTY_CASH_SETTLEMENT_STEPS,
    WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
)
from app.core.database import SessionLocal
from app.services.workflow_definition_service import upsert_definition


def main() -> None:
    db = SessionLocal()
    try:
        upsert_definition(
            db,
            ref_type=WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
            name="تأیید خرج تنخواه",
            steps=list(PETTY_CASH_SETTLEMENT_STEPS),
        )
        print(f"OK: workflow_definitions.{WORKFLOW_REF_PETTY_CASH_SETTLEMENT}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
