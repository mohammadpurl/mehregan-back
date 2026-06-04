"""گزارش تجمیعی مالی برای مدیرعامل و مدیر مالی."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.petty_cash import (
    SETTLEMENT_PENDING,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep


def _day_range(d: date | None) -> tuple[datetime | None, datetime | None]:
    if d is None:
        return None, None
    start = datetime.combine(d, time.min)
    end = datetime.combine(d, time.max)
    return start, end


def get_executive_financial_report(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    pr_q = db.query(PaymentRequest)
    pc_q = db.query(PettyCashRequest)

    if date_from:
        pr_q = pr_q.filter(PaymentRequest.created_at >= datetime.combine(date_from, time.min))
        pc_q = pc_q.filter(PettyCashRequest.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        pr_q = pr_q.filter(PaymentRequest.created_at <= datetime.combine(date_to, time.max))
        pc_q = pc_q.filter(PettyCashRequest.created_at <= datetime.combine(date_to, time.max))

    pr_rows = pr_q.all()
    pc_rows = pc_q.all()

    def _sum_amount(rows, attr="amount"):
        return float(sum(float(getattr(r, attr) or 0) for r in rows))

    pr_by_status: dict[str, int] = {}
    pr_amount_by_status: dict[str, float] = {}
    for r in pr_rows:
        st = (r.status or "UNKNOWN").upper()
        pr_by_status[st] = pr_by_status.get(st, 0) + 1
        pr_amount_by_status[st] = pr_amount_by_status.get(st, 0.0) + float(r.amount or 0)

    pc_by_status: dict[str, int] = {}
    pc_amount_by_status: dict[str, float] = {}
    for r in pc_rows:
        st = (r.status or "UNKNOWN").upper()
        pc_by_status[st] = pc_by_status.get(st, 0) + 1
        pc_amount_by_status[st] = pc_amount_by_status.get(st, 0.0) + float(r.amount or 0)

    pc_settlement_pending = sum(
        1
        for r in pc_rows
        if r.status == STATUS_APPROVED and r.settlement_status == SETTLEMENT_PENDING
    )

    wf_pending = (
        db.query(func.count(WorkflowInstance.id))
        .filter(WorkflowInstance.status.in_(("pending", "in_progress", "active")))
        .scalar()
        or 0
    )

    financial_wf_pending = (
        db.query(func.count(WorkflowInstance.id))
        .filter(
            WorkflowInstance.ref_type.in_(("payment_request", "petty_cash")),
            WorkflowInstance.status.in_(("pending", "in_progress", "active")),
        )
        .scalar()
        or 0
    )

    inbox_financial_steps = (
        db.query(func.count(WorkflowStep.id))
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowStep.instance_id)
        .filter(
            WorkflowStep.status == "pending",
            WorkflowInstance.ref_type.in_(("payment_request", "petty_cash")),
        )
        .scalar()
        or 0
    )

    return {
        "period": {"from": date_from.isoformat() if date_from else None, "to": date_to.isoformat() if date_to else None},
        "payment_requests": {
            "total": len(pr_rows),
            "by_status": pr_by_status,
            "amount_by_status": {k: round(v, 2) for k, v in pr_amount_by_status.items()},
            "total_amount": round(_sum_amount(pr_rows), 2),
            "pending_count": pr_by_status.get("PENDING", 0),
            "approved_count": pr_by_status.get("APPROVED", 0),
            "rejected_count": pr_by_status.get("REJECTED", 0),
        },
        "petty_cash": {
            "total": len(pc_rows),
            "by_status": pc_by_status,
            "amount_by_status": {k: round(v, 2) for k, v in pc_amount_by_status.items()},
            "total_amount": round(_sum_amount(pc_rows), 2),
            "pending_count": pc_by_status.get(STATUS_PENDING, 0),
            "approved_count": pc_by_status.get(STATUS_APPROVED, 0),
            "rejected_count": pc_by_status.get(STATUS_REJECTED, 0),
            "awaiting_settlement_count": pc_settlement_pending,
        },
        "workflow": {
            "all_pending_instances": wf_pending,
            "financial_pending_instances": financial_wf_pending,
            "financial_pending_steps": inbox_financial_steps,
        },
    }
