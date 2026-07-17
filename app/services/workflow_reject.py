"""رد مرحله گردش‌کار با بازگشت به مرحله قبل یا درخواست‌کننده."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.infrastructure.messaging.events import WORKFLOW_REJECTED
from app.infrastructure.messaging.publisher import publish_event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import mark_inbox_done_for_workflow
from app.services.workflow_approval_log import record_workflow_decision
from app.services.workflow_notifications import (
    notify_submitter_step_decision,
    notify_workflow_next_step,
    notify_workflow_rejected,
)
from app.services.workflow_step_access import user_can_act_on_workflow_step

RETURN_TO_PREVIOUS = "previous"
RETURN_TO_REQUESTER = "requester"
RETURN_TARGETS = frozenset({RETURN_TO_PREVIOUS, RETURN_TO_REQUESTER})


def _pending_step(db: Session, instance_id: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter_by(instance_id=instance_id, status="pending")
        .order_by(WorkflowStep.order)
        .first()
    )


def _sync_business_on_return_to_requester(db: Session, inst: WorkflowInstance) -> None:
    if not inst.ref_type or not inst.ref_id:
        return
    ref_type = str(inst.ref_type)
    ref_id = int(inst.ref_id)

    if ref_type == "financial_document":
        from app.services.financial_document import on_workflow_rejected

        on_workflow_rejected(db, ref_id)
        return

    if ref_type == "petty_cash":
        from app.services.petty_cash import on_workflow_rejected

        on_workflow_rejected(db, ref_id)
        return

    if ref_type == "petty_cash_settlement":
        from app.services.petty_cash import on_settlement_workflow_rejected

        on_settlement_workflow_rejected(db, ref_id)
        return

    if ref_type == "mission_request":
        from app.services.mission_request import on_workflow_rejected

        on_workflow_rejected(db, ref_id)
        return

    if ref_type == "mission_report":
        from app.services.mission_request import on_report_workflow_rejected

        on_report_workflow_rejected(db, ref_id)
        return

    if ref_type == "request":
        from app.constants.procurement import STATUS_PENDING
        from app.models.request import Request

        req = db.get(Request, ref_id)
        if req:
            req.status = STATUS_PENDING
        return

    if ref_type in ("payment_request", "payment_order"):
        from app.models.payment_request import PaymentRequest

        pr = db.get(PaymentRequest, ref_id)
        if pr:
            pr.status = "PENDING"


def reject_step(
    db: Session,
    instance_id: int,
    user,
    *,
    comment: str | None = None,
    return_to: str = RETURN_TO_PREVIOUS,
) -> WorkflowInstance:
    # سیاست محصول: رد همیشه به مرحله قبل؛ فقط مرحلهٔ ۱ به درخواست‌کننده برمی‌گردد.
    target = (return_to or RETURN_TO_PREVIOUS).strip().lower()
    if target not in RETURN_TARGETS:
        raise ValueError("return_to must be 'previous' or 'requester'")
    if not comment or not str(comment).strip():
        raise ValueError("ثبت دلیل رد (کامنت) الزامی است")

    step = _pending_step(db, instance_id)
    if not step:
        raise ValueError("no pending step")

    if not user_can_act_on_workflow_step(user, step):
        raise ValueError("access denied")

    instance = db.get(WorkflowInstance, instance_id)
    if not instance:
        raise ValueError("workflow instance not found")

    # مرحله قبل = آخرین مرحلهٔ موجود با order کمتر (نه لزوماً order-1؛
    # چون با skip مدیر مستقیم ممکن است شمارهٔ مراحل در نمونه پیوسته نباشد)
    prev = (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.instance_id == instance_id,
            WorkflowStep.order < step.order,
        )
        .order_by(WorkflowStep.order.desc())
        .first()
    )
    if prev:
        target = RETURN_TO_PREVIOUS
    else:
        target = RETURN_TO_REQUESTER

    step.status = "rejected"
    step.approved_by = user.id
    step.approved_at = datetime.utcnow()
    from app.services.sla import close_sla_for_instance, close_sla_for_step

    close_sla_for_step(db, step.id)
    record_workflow_decision(
        db,
        instance_id=instance_id,
        step_id=step.id,
        approved_by=user.id,
        decision="rejected",
        comment=comment.strip(),
    )
    mark_inbox_done_for_workflow(db, instance_id, user_id=user.id)

    rejected_step_order = step.order

    if target == RETURN_TO_PREVIOUS and prev:
        prev.status = "pending"
        prev.approved_by = None
        prev.approved_at = None
        instance.status = "in_progress"
        db.commit()
        if prev.assigned_user_id or prev.role_id:
            notify_workflow_next_step(
                db,
                {
                    "instance_id": instance_id,
                    "role_id": prev.role_id,
                    "step_id": prev.id,
                    "user_id": prev.assigned_user_id,
                },
            )
        notify_submitter_step_decision(
            db,
            instance_id=instance_id,
            decision="rejected",
            step_order=rejected_step_order,
            actor=user,
            comment=comment.strip(),
            returned_to_previous=True,
            create_inbox=False,
        )
        db.commit()
        return instance

    instance.status = "returned"
    _sync_business_on_return_to_requester(db, instance)
    close_sla_for_instance(db, instance_id)
    db.commit()

    notify_workflow_rejected(
        db,
        instance_id=instance_id,
        rejected_by_user_id=user.id,
        comment=comment.strip(),
        step_order=rejected_step_order,
        actor=user,
    )

    rejected_payload: dict = {
        "instance_id": instance_id,
        "user_id": user.id,
        "return_to": target,
    }
    if instance.ref_type:
        rejected_payload["ref_type"] = instance.ref_type
        rejected_payload["ref_id"] = instance.ref_id
    publish_event(WORKFLOW_REJECTED, rejected_payload)
    db.commit()
    return instance
