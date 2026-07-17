"""
گردش‌کار تأیید گزارش ماموریت: مدیر مستقیم → مدیرعامل

  python scripts/seed_mission_report_workflow.py
  python scripts/seed_mission_report_workflow.py --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.mission_request import (
    MISSION_REPORT_STEPS,
    WORKFLOW_REF_MISSION_REPORT,
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
            ref_type=WORKFLOW_REF_MISSION_REPORT,
            name="تأیید گزارش ماموریت",
            steps=list(MISSION_REPORT_STEPS),
            force=args.force,
        )
        if row:
            print(f"OK: workflow_definitions.{WORKFLOW_REF_MISSION_REPORT} created/updated")
        else:
            print(
                f"SKIP: workflow_definitions.{WORKFLOW_REF_MISSION_REPORT} "
                "already exists (admin edits preserved)"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
