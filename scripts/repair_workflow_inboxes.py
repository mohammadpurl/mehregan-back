"""
ایجاد کارتابل/اعلان برای مراحل pending گردش‌کار که inbox باز ندارند.

  python scripts/repair_workflow_inboxes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import find_open_workflow_inbox
from app.services.workflow_notifications import notify_workflow_next_step


def main() -> None:
    db = SessionLocal()
    repaired = 0
    try:
        instances = (
            db.query(WorkflowInstance)
            .filter(WorkflowInstance.status.in_(("pending", "in_progress", "active")))
            .all()
        )
        for inst in instances:
            step = (
                db.query(WorkflowStep)
                .filter(
                    WorkflowStep.instance_id == inst.id,
                    WorkflowStep.status == "pending",
                )
                .order_by(WorkflowStep.order)
                .first()
            )
            if not step or not step.assigned_user_id:
                continue
            uid = int(step.assigned_user_id)
            if find_open_workflow_inbox(db, instance_id=inst.id, user_id=uid):
                continue
            payload = {
                "instance_id": inst.id,
                "role_id": step.role_id,
                "step_id": step.id,
                "user_id": uid,
            }
            notify_workflow_next_step(db, payload)
            repaired += 1
            print(
                f"OK instance={inst.id} ref={inst.ref_type}/{inst.ref_id} "
                f"step={step.order} user_id={uid}"
            )
        db.commit()
        print(f"Repaired {repaired} workflow inbox(es).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
