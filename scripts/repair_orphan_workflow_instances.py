"""Cancel workflow instances whose business record no longer exists."""

from __future__ import annotations

import argparse

from app.core.database import SessionLocal
from app.models.inbox import InboxItem
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep


def _business_exists(db, inst: WorkflowInstance) -> bool:
    ref_type = (inst.ref_type or "").strip()
    if ref_type == "payment_request":
        return db.get(PaymentRequest, inst.ref_id) is not None
    if ref_type == "petty_cash":
        return db.get(PettyCashRequest, inst.ref_id) is not None
    return True


def repair_orphans(*, dry_run: bool) -> int:
    db = SessionLocal()
    repaired = 0
    try:
        instances = (
            db.query(WorkflowInstance)
            .filter(WorkflowInstance.status.in_(("pending", "in_progress", "active")))
            .all()
        )
        for inst in instances:
            if _business_exists(db, inst):
                continue
            repaired += 1
            print(
                f"orphan inst={inst.id} ref_type={inst.ref_type} ref_id={inst.ref_id} status={inst.status}"
            )
            if dry_run:
                continue
            inst.status = "cancelled"
            for step in db.query(WorkflowStep).filter_by(instance_id=inst.id).all():
                if step.status == "pending":
                    step.status = "cancelled"
            for inbox in (
                db.query(InboxItem)
                .filter(
                    InboxItem.ref_type == "workflow",
                    InboxItem.ref_id == inst.id,
                    InboxItem.is_done == False,  # noqa: E712
                )
                .all()
            ):
                inbox.is_done = True
        if not dry_run and repaired:
            db.commit()
        elif dry_run:
            db.rollback()
    finally:
        db.close()
    return repaired


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    count = repair_orphans(dry_run=args.dry_run)
    suffix = " (dry run)" if args.dry_run else ""
    print(f"Done. Orphan instances handled: {count}{suffix}")


if __name__ == "__main__":
    main()
