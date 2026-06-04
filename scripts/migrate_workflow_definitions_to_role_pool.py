"""
تبدیل تعاریف گردش‌کار قدیمی (submitter_manager / department_head) به role_pool.

  python scripts/migrate_workflow_definitions_to_role_pool.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.workflow_definition import WorkflowDefinition
from app.services.workflow_step_config import (
    DEPARTMENT_HEAD,
    SUBMITTER_MANAGER,
    normalize_steps_config,
)

LEGACY = {SUBMITTER_MANAGER, DEPARTMENT_HEAD}


def main() -> None:
    db = SessionLocal()
    updated = 0
    try:
        rows = db.query(WorkflowDefinition).all()
        for row in rows:
            if not isinstance(row.steps_config, list) or not row.steps_config:
                continue
            changed = False
            raw_steps = []
            for step in row.steps_config:
                if isinstance(step, dict):
                    s = dict(step)
                    strat = str(
                        s.get("assignee_strategy") or s.get("assigneeStrategy") or ""
                    ).lower()
                    if strat in LEGACY:
                        s["assignee_strategy"] = "role_pool"
                        s.pop("assigneeStrategy", None)
                        changed = True
                    raw_steps.append(s)
                else:
                    raw_steps.append(step)
            if not changed:
                continue
            row.steps_config = normalize_steps_config(raw_steps)
            updated += 1
            print(f"OK ref_type={row.ref_type}")
        db.commit()
        print(f"Migrated {updated} workflow definition(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
