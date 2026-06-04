"""
حذف کامل همه درخواست‌های مالی (payment_requests) و workflow/inbox/notification مرتبط.

اجرا:
  python scripts/reset_financial_requests.py --dry-run
  python scripts/reset_financial_requests.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.attachment import Attachment
from app.models.inbox import InboxItem
from app.models.notification import Notification
from app.models.payment_request import PaymentRequest
from app.models.workflow_approval import WorkflowApproval
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.attachment_service import ENTITY_PAYMENT_REQUEST
from app.services.workflow_cleanup import cancel_workflow_instance


def reset_financial_requests(*, dry_run: bool) -> dict[str, int]:
    db = SessionLocal()
    stats = {
        "payment_requests": 0,
        "attachments": 0,
        "workflow_instances": 0,
        "workflow_steps": 0,
        "workflow_approvals": 0,
        "inbox_items": 0,
        "notifications": 0,
    }
    try:
        pr_ids = [row[0] for row in db.execute(select(PaymentRequest.id)).all()]
        stats["payment_requests"] = len(pr_ids)

        instance_ids = [
            row[0]
            for row in db.execute(
                select(WorkflowInstance.id).where(
                    WorkflowInstance.ref_type == "payment_request"
                )
            ).all()
        ]
        stats["workflow_instances"] = len(instance_ids)

        for iid in instance_ids:
            cancel_workflow_instance(db, iid)

        if pr_ids:
            att_count = (
                db.query(Attachment)
                .filter(
                    Attachment.entity_type == ENTITY_PAYMENT_REQUEST,
                    Attachment.entity_id.in_(pr_ids),
                )
                .count()
            )
            stats["attachments"] = att_count
            if not dry_run:
                db.execute(
                    delete(Attachment).where(
                        Attachment.entity_type == ENTITY_PAYMENT_REQUEST,
                        Attachment.entity_id.in_(pr_ids),
                    )
                )
                db.execute(delete(PaymentRequest).where(PaymentRequest.id.in_(pr_ids)))

        if instance_ids:
            stats["workflow_steps"] = (
                db.query(WorkflowStep)
                .filter(WorkflowStep.instance_id.in_(instance_ids))
                .count()
            )
            stats["workflow_approvals"] = (
                db.query(WorkflowApproval)
                .filter(WorkflowApproval.instance_id.in_(instance_ids))
                .count()
            )
            stats["inbox_items"] = (
                db.query(InboxItem)
                .filter(
                    InboxItem.ref_type == "workflow",
                    InboxItem.ref_id.in_(instance_ids),
                )
                .count()
            )
            stats["notifications"] = (
                db.query(Notification)
                .filter(
                    Notification.ref_type == "workflow",
                    Notification.ref_id.in_(instance_ids),
                )
                .count()
            )
            if not dry_run:
                db.execute(
                    delete(WorkflowApproval).where(
                        WorkflowApproval.instance_id.in_(instance_ids)
                    )
                )
                db.execute(
                    delete(WorkflowStep).where(WorkflowStep.instance_id.in_(instance_ids))
                )
                db.execute(
                    delete(InboxItem).where(
                        InboxItem.ref_type == "workflow",
                        InboxItem.ref_id.in_(instance_ids),
                    )
                )
                db.execute(
                    delete(Notification).where(
                        Notification.ref_type == "workflow",
                        Notification.ref_id.in_(instance_ids),
                    )
                )
                db.execute(
                    delete(WorkflowInstance).where(WorkflowInstance.id.in_(instance_ids))
                )

        if dry_run:
            db.rollback()
            print("DRY RUN - no changes committed.")
        else:
            db.commit()
            print("Committed.")
    finally:
        db.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset all payment/financial requests")
    parser.add_argument("--yes", action="store_true", help="اجرای واقعی (بدون --yes فقط dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="فقط نمایش آمار")
    args = parser.parse_args()
    dry_run = not args.yes or args.dry_run
    if not args.yes and not args.dry_run:
        print("Run with: python scripts/reset_financial_requests.py --yes")
        dry_run = True

    stats = reset_financial_requests(dry_run=dry_run)
    print("Stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
