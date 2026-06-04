"""
راه‌اندازی مجدد workflow برای درخواست‌های مالی بدون نمونه گردش‌کار (بعد از خطای consumer).

  python scripts/replay_payment_request_workflows.py --dry-run
  python scripts/replay_payment_request_workflows.py --yes
  python scripts/replay_payment_request_workflows.py --yes --payment-request-id 12
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.services.workflow_start import start_workflow_instance
from app.models.payment_request import PaymentRequest
from app.models.workflow_instance import WorkflowInstance


def find_orphan_payment_requests(db, payment_request_id: int | None) -> list[PaymentRequest]:
    q = db.query(PaymentRequest).order_by(PaymentRequest.id.desc())
    if payment_request_id is not None:
        q = q.filter(PaymentRequest.id == payment_request_id)
    rows = q.all()
    out: list[PaymentRequest] = []
    for pr in rows:
        inst = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.ref_type == "payment_request",
                WorkflowInstance.ref_id == pr.id,
            )
            .first()
        )
        if inst is None:
            out.append(pr)
    return out


def replay_one(db, pr: PaymentRequest, *, dry_run: bool) -> None:
    payload = {
        "ref_type": "payment_request",
        "ref_id": pr.id,
        "submitter_id": pr.requester_id,
    }
    print(f"  PR #{pr.id} requester_id={pr.requester_id} type={pr.payment_type}")
    if dry_run:
        return
    start_workflow_instance(db, payload, sync_notify=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--payment-request-id", type=int, default=None)
    args = parser.parse_args()
    dry_run = not args.yes or args.dry_run

    db = SessionLocal()
    try:
        orphans = find_orphan_payment_requests(db, args.payment_request_id)
        if not orphans:
            print("No payment requests without workflow instance.")
            return
        print(f"Found {len(orphans)} orphan payment request(s).")
        if dry_run:
            print("DRY RUN")
        for pr in orphans:
            replay_one(db, pr, dry_run=dry_run)
        if not dry_run:
            db.commit()
            print("Done. Restart consumer if it was running with old code.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
