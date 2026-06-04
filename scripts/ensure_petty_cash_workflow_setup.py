"""
نقش‌های تنخواه (مدیر مالی، مدیرعامل) و تعمیر instanceهای معلق.

  python scripts/ensure_petty_cash_workflow_setup.py --finance-user-id 2 --ceo-user-id 3
  python scripts/ensure_petty_cash_workflow_setup.py --repair-instances
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.petty_cash_request import PettyCashRequest
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_definition_service import get_steps_config, upsert_definition
from app.services.workflow_step_config import (
    resolve_role_id_for_step,
    resolve_step_assignee_user,
)
from scripts.seed_petty_cash_workflow import STEPS


def _grant_role(db, role_name: str, user_id: int) -> bool:
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        print(f"WARN: role {role_name} not found")
        return False
    existing = (
        db.query(UserRole)
        .filter(
            UserRole.role_id == role.id,
            UserRole.user_id == user_id,
            UserRole.is_active == True,  # noqa: E712
        )
        .first()
    )
    if existing:
        print(f"OK: {role_name} already on user_id={user_id}")
        return False
    db.add(UserRole(user_id=user_id, role_id=role.id, is_active=True))
    print(f"Granted {role_name} to user_id={user_id}")
    return True


def repair_pending_instances(db) -> int:
    fixed = 0
    steps_config = get_steps_config(db, "petty_cash")
    instances = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == "petty_cash",
            WorkflowInstance.status == "pending",
        )
        .all()
    )
    for inst in instances:
        pc = db.get(PettyCashRequest, inst.ref_id)
        submitter_id = pc.requester_id if pc else None
        steps = (
            db.query(WorkflowStep)
            .filter_by(instance_id=inst.id)
            .order_by(WorkflowStep.order)
            .all()
        )
        assigned_so_far: list[int] = []
        for step, cfg in zip(steps, steps_config):
            if step.status != "pending":
                if step.assigned_user_id:
                    assigned_so_far.append(step.assigned_user_id)
                continue
            role_id = resolve_role_id_for_step(db, cfg)
            new_assignee = resolve_step_assignee_user(
                db,
                cfg,
                role_id=role_id,
                submitter_id=submitter_id,
                exclude_user_ids=assigned_so_far,
            )
            new_id = new_assignee.id if new_assignee else None
            if new_id and new_id != step.assigned_user_id:
                print(
                    f"instance {inst.id} step {step.order}: "
                    f"{step.assigned_user_id} -> {new_id}"
                )
                step.assigned_user_id = new_id
                fixed += 1
            if new_id:
                assigned_so_far.append(new_id)
    if fixed:
        db.commit()
    return fixed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finance-user-id", type=int, default=None)
    parser.add_argument("--ceo-user-id", type=int, default=None)
    parser.add_argument("--repair-instances", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        upsert_definition(
            db,
            ref_type="petty_cash",
            name="درخواست تنخواه",
            steps=STEPS,
        )
        print("OK: workflow_definitions.petty_cash")

        changed = False
        if args.finance_user_id is not None:
            changed |= _grant_role(db, "finance_manager", args.finance_user_id)
        if args.ceo_user_id is not None:
            changed |= _grant_role(db, "ceo", args.ceo_user_id)
        if changed:
            db.commit()

        if args.repair_instances:
            n = repair_pending_instances(db)
            print(f"Repaired {n} step assignment(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
