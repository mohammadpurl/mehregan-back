"""
تعریف workflow درخواست ماموریت: مدیر مستقیم → مدیرعامل

  python scripts/seed_mission_request_workflow.py
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
        "label": "تأیید مدیر مستقیم",
        "role_aliases": ["manager", "project_manager", "مدیر مستقیم", "مدیر واحد"],
        "assignee_strategy": "submitter_manager",
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
            ref_type="mission_request",
            name="درخواست ماموریت",
            steps=STEPS,
        )
        print("OK: workflow_definitions.mission_request")
    finally:
        db.close()


if __name__ == "__main__":
    main()
