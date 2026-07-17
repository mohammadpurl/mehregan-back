from __future__ import annotations

import argparse
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
from app.services.workflow_definition_service import ensure_definition


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="بازنویسی تعریف موجود (تغییرات ادمین پاک می‌شود)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        row = ensure_definition(
            db,
            ref_type=WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
            name="تأیید خرج تنخواه",
            steps=list(PETTY_CASH_SETTLEMENT_STEPS),
            force=args.force,
        )
        if row:
            print(f"OK: workflow_definitions.{WORKFLOW_REF_PETTY_CASH_SETTLEMENT} created/updated")
        else:
            print(
                f"SKIP: workflow_definitions.{WORKFLOW_REF_PETTY_CASH_SETTLEMENT} "
                "already exists (admin edits preserved)"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
