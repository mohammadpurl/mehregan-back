"""
تنظیم workflow وام/مساعده + نقش finance_manager برای حداقل یک کاربر.

  python scripts/ensure_payment_workflow_setup.py
  python scripts/ensure_payment_workflow_setup.py --finance-user-id 6
  python scripts/ensure_payment_workflow_setup.py --repair-instances
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_definition_service import get_steps_config, upsert_definition
from app.services.workflow_step_config import (
    resolve_role_id_for_step,
    resolve_step_assignee_user,
)

PAYMENT_REQUEST_STEPS = [
    {
        "order": 1,
        "label": "تأیید مدیر مستقیم",
        "role_aliases": ["manager", "project_manager", "مدیر پروژه", "مدیر مستقیم"],
        "assignee_strategy": "submitter_manager",
    },
    {
        "order": 2,
        "label": "تأیید مدیر مالی",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
    },
]


def ensure_finance_role(db, finance_user_id: int | None) -> int | None:
    role = db.query(Role).filter(Role.name == "finance_manager").first()
    if not role:
        print("WARN: role finance_manager not found — run scripts/reset_rbac.py")
        return None

    existing = (
        db.query(UserRole)
        .filter(UserRole.role_id == role.id, UserRole.is_active == True)  # noqa: E712
        .first()
    )
    if existing:
        print(f"OK: finance_manager already assigned to user_id={existing.user_id}")
        return existing.user_id

    if finance_user_id is None:
        print("WARN: no finance_manager user — pass --finance-user-id <id>")
        return None

    db.add(
        UserRole(user_id=finance_user_id, role_id=role.id, is_active=True)
    )
    db.commit()
    print(f"Granted finance_manager to user_id={finance_user_id}")
    return finance_user_id


def repair_pending_instances(db) -> int:
    """مرحله مالی را دوباره assign کن اگر با مدیر مستقیم یکی شده."""
    fixed = 0
    instances = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == "payment_request",
            WorkflowInstance.status == "pending",
        )
        .all()
    )
    steps_config = get_steps_config(db, "payment_request")
    if len(steps_config) < 2:
        return 0

    for inst in instances:
        steps = (
            db.query(WorkflowStep)
            .filter_by(instance_id=inst.id)
            .order_by(WorkflowStep.order)
            .all()
        )
        if len(steps) < 2:
            continue
        s1, s2 = steps[0], steps[1]
        if s1.status != "pending" or s2.status != "pending":
            continue
        if not s1.assigned_user_id or s1.assigned_user_id != s2.assigned_user_id:
            continue

        from app.models.payment_request import PaymentRequest

        pr = db.get(PaymentRequest, inst.ref_id)
        submitter_id = pr.requester_id if pr else None
        cfg = steps_config[1]
        role_id = resolve_role_id_for_step(db, cfg)
        new_assignee = resolve_step_assignee_user(
            db,
            cfg,
            role_id=role_id,
            submitter_id=submitter_id,
            exclude_user_ids=[s1.assigned_user_id] if s1.assigned_user_id else [],
        )
        new_id = new_assignee.id if new_assignee else None
        if new_id and new_id != s2.assigned_user_id:
            s2.assigned_user_id = new_id
            fixed += 1
            print(
                f"instance {inst.id}: step 2 assignee "
                f"{s1.assigned_user_id} -> {new_id}"
            )
    if fixed:
        db.commit()
    return fixed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finance-user-id", type=int, default=None)
    parser.add_argument("--repair-instances", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        upsert_definition(
            db,
            ref_type="payment_request",
            name="درخواست مالی (وام/مساعده/پرداخت)",
            steps=PAYMENT_REQUEST_STEPS,
        )
        print("OK: workflow_definitions.payment_request updated")

        ensure_finance_role(db, args.finance_user_id)

        if args.repair_instances:
            n = repair_pending_instances(db)
            print(f"Repaired {n} pending instance(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
