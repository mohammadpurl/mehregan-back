"""
گردش‌کار تأیید گزارش ماموریت: مدیر مستقیم → مدیرعامل

  python scripts/seed_mission_report_workflow.py
"""

from __future__ import annotations

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
from app.services.workflow_definition_service import upsert_definition


def main() -> None:
    db = SessionLocal()
    try:
        upsert_definition(
            db,
            ref_type=WORKFLOW_REF_MISSION_REPORT,
            name="تأیید گزارش ماموریت",
            steps=list(MISSION_REPORT_STEPS),
        )
        print(f"OK: workflow_definitions.{WORKFLOW_REF_MISSION_REPORT}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
