from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.financial_workflow import UNIFIED_FINANCIAL_STEPS
from app.core.database import SessionLocal
from app.services.workflow_definition_service import ensure_definition

STEPS = list(UNIFIED_FINANCIAL_STEPS)


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
            ref_type="financial_document",
            name="اسناد مالی",
            steps=STEPS,
            force=args.force,
        )
        if row:
            print("OK: workflow_definitions.financial_document created/updated")
        else:
            print("SKIP: workflow_definitions.financial_document already exists (admin edits preserved)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
