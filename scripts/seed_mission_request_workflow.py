from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.services.workflow_definition_service import ensure_definition

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
            ref_type="mission_request",
            name="درخواست ماموریت",
            steps=STEPS,
            force=args.force,
        )
        if row:
            print("OK: workflow_definitions.mission_request created/updated")
        else:
            print("SKIP: workflow_definitions.mission_request already exists (admin edits preserved)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
