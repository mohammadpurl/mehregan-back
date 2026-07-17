"""
تعریف گردش‌کار ۵مرحله‌ای دستور پرداخت (ref_type=payment_order).

  python scripts/ensure_payment_order_workflow_setup.py
  python scripts/ensure_payment_order_workflow_setup.py --repair-instances
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_definition_service import get_steps_config
from app.services.workflow_step_config import (
    resolve_role_id_for_step,
    resolve_step_assignee_user,
)

from app.constants.financial_workflow import UNIFIED_FINANCIAL_STEPS

PAYMENT_ORDER_STEPS = list(UNIFIED_FINANCIAL_STEPS)


def repair_pending_instances(db) -> int:
    """مراحل مالی/کارشناسی را در صورت تداخل assignee با مرحله قبل اصلاح می‌کند."""
    fixed = 0
    instances = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == "payment_order",
            WorkflowInstance.status.in_(("pending", "in_progress", "active")),
        )
        .all()
    )
    steps_config = get_steps_config(db, "payment_order")
    if len(steps_config) < 2:
        return 0

    from app.models.payment_request import PaymentRequest

    for inst in instances:
        steps = (
            db.query(WorkflowStep)
            .filter_by(instance_id=inst.id)
            .order_by(WorkflowStep.order)
            .all()
        )
        if len(steps) < 2:
            continue
        pending = [s for s in steps if s.status == "pending"]
        if len(pending) < 2:
            continue
        prev_approved = max(
            (s for s in steps if s.status == "approved"),
            key=lambda s: s.order,
            default=None,
        )
        if not prev_approved or not prev_approved.assigned_user_id:
            continue
        cur = pending[0]
        if cur.assigned_user_id != prev_approved.assigned_user_id:
            continue
        if cur.order >= len(steps_config):
            continue

        pr = db.get(PaymentRequest, inst.ref_id)
        submitter_id = pr.requester_id if pr else None
        cfg = steps_config[cur.order - 1]
        role_id = resolve_role_id_for_step(db, cfg)
        new_assignee = resolve_step_assignee_user(
            db,
            cfg,
            role_id=role_id,
            submitter_id=submitter_id,
            exclude_user_ids=[prev_approved.assigned_user_id],
        )
        new_id = new_assignee.id if new_assignee else None
        if new_id and new_id != cur.assigned_user_id:
            cur.assigned_user_id = new_id
            fixed += 1
            print(f"  instance {inst.id} step {cur.order}: assignee -> user {new_id}")

    if fixed:
        db.commit()
    return fixed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-instances", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="بازنویسی تعریف موجود (تغییرات ادمین پاک می‌شود)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        from app.services.workflow_definition_service import ensure_definition

        row = ensure_definition(
            db,
            ref_type="payment_order",
            name="دستور پرداخت",
            steps=PAYMENT_ORDER_STEPS,
            force=args.force,
        )
        if row:
            print("OK: workflow definition payment_order created/updated")
        else:
            print("SKIP: payment_order already exists (admin edits preserved)")

        if args.repair_instances:
            n = repair_pending_instances(db)
            print(f"Repaired {n} instance step assignee(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
