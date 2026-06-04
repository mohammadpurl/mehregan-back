"""گردش‌کار دستور پرداخت (ref_type=payment_order)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.constants.payment_order import (
    ACTION_APPROVAL,
    ACTION_FINAL_PAYMENT_APPROVAL,
    ACTION_MARK_PAYMENT,
    WORKFLOW_REF_PAYMENT_ORDER,
)
from app.constants.payment_types import PAYMENT_TYPE_PAYMENT_ORDER
from app.infrastructure.messaging.events import WORKFLOW_APPROVED, WORKFLOW_NEXT_STEP
from app.infrastructure.messaging.publisher import publish_event
from app.models.payment_request import PaymentRequest
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import mark_inbox_done_for_workflow
from app.services.workflow_approval_log import record_workflow_decision
from app.services.workflow_notifications import notify_workflow_next_step
from app.services.workflow_step_access import user_can_act_on_workflow_step
from app.services.workflow_step_config import get_step_config_at_order

_ACTIVE_STATUSES = ("pending", "in_progress", "active")


def step_action_for_order(db: Session, order: int) -> str:
    cfg = get_step_config_at_order(db, WORKFLOW_REF_PAYMENT_ORDER, order)
    if not cfg:
        return ACTION_APPROVAL
    action = (cfg.get("step_action") or ACTION_APPROVAL).strip()
    return action or ACTION_APPROVAL


def workflow_instance_for_payment_order(
    db: Session, payment_request_id: int
) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == WORKFLOW_REF_PAYMENT_ORDER,
            WorkflowInstance.ref_id == payment_request_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def _pending_step(db: Session, instance_id: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter_by(instance_id=instance_id, status="pending")
        .order_by(WorkflowStep.order)
        .first()
    )


def _complete_step_record(
    db: Session,
    step: WorkflowStep,
    user: User,
    *,
    comment: str | None = None,
) -> None:
    from app.services.sla import close_sla_for_step

    step.status = "approved"
    step.approved_by = user.id
    step.approved_at = datetime.utcnow()
    close_sla_for_step(db, step.id)
    record_workflow_decision(
        db,
        instance_id=step.instance_id,
        step_id=step.id,
        approved_by=user.id,
        decision="approved",
        comment=comment,
    )


def _notify_next(db: Session, instance: WorkflowInstance, step: WorkflowStep) -> None:
    payload = {
        "instance_id": instance.id,
        "role_id": step.role_id,
        "step_id": step.id,
        "user_id": step.assigned_user_id,
    }
    notify_workflow_next_step(db, payload)
    publish_event(WORKFLOW_NEXT_STEP, payload)


def complete_mark_payment_step(
    db: Session,
    *,
    payment_request_id: int,
    user: User,
    comment: str | None = None,
) -> None:
    inst = workflow_instance_for_payment_order(db, payment_request_id)
    if not inst or inst.status not in _ACTIVE_STATUSES:
        raise ValueError("گردش‌کار فعال یافت نشد")
    step = _pending_step(db, inst.id)
    if not step:
        raise ValueError("مرحله‌ای در انتظار نیست")
    action = step_action_for_order(db, step.order)
    if action != ACTION_MARK_PAYMENT:
        raise ValueError("این مرحله «ثبت پرداخت» نیست")
    if not user_can_act_on_workflow_step(user, step):
        raise ValueError("دسترسی به این مرحله مجاز نیست")

    pr = db.get(PaymentRequest, payment_request_id)
    if not pr or pr.payment_type != PAYMENT_TYPE_PAYMENT_ORDER:
        raise ValueError("دستور پرداخت یافت نشد")

    pr.payment_marked_at = datetime.utcnow()
    pr.payment_marked_by = user.id
    _complete_step_record(db, step, user, comment=comment or "پرداخت انجام شد")
    mark_inbox_done_for_workflow(db, inst.id, user_id=user.id)
    db.flush()

    advance_workflow_after_step(
        db,
        instance_id=inst.id,
        completed_order=step.order,
        actor=user,
    )


def assert_can_approve_pending_step(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    *,
    payment_executed: bool = False,
) -> None:
    action = step_action_for_order(db, step.order)
    if action == ACTION_MARK_PAYMENT:
        raise ValueError(
            "ثبت پرداخت از دکمه «پرداخت انجام شد» انجام می‌شود، نه تأیید معمول کارتابل"
        )
    if action == ACTION_FINAL_PAYMENT_APPROVAL:
        pr = db.get(PaymentRequest, instance.ref_id)
        if not pr or not pr.payment_marked_at:
            raise ValueError("ابتدا کارشناس مالی باید «پرداخت انجام شد» را ثبت کند")
    if payment_executed:
        raise ValueError("از دکمه ثبت پرداخت استفاده کنید")


def try_complete_operational_from_inbox(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    user: User,
    *,
    payment_executed: bool = False,
) -> bool:
    if instance.ref_type != WORKFLOW_REF_PAYMENT_ORDER:
        return False
    if step_action_for_order(db, step.order) != ACTION_MARK_PAYMENT:
        return False
    if not payment_executed:
        return False
    complete_mark_payment_step(
        db, payment_request_id=int(instance.ref_id), user=user, comment="پرداخت انجام شد"
    )
    return True


def advance_workflow_after_step(
    db: Session,
    *,
    instance_id: int,
    completed_order: int,
    actor: User,
) -> None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type != WORKFLOW_REF_PAYMENT_ORDER:
        return

    next_step = _pending_step(db, instance_id)
    if next_step:
        _notify_next(db, inst, next_step)
        db.commit()
        return

    inst.status = "approved"
    db.commit()
    publish_event(
        WORKFLOW_APPROVED,
        {
            "instance_id": inst.id,
            "ref_type": WORKFLOW_REF_PAYMENT_ORDER,
            "ref_id": inst.ref_id,
            "user_id": actor.id,
        },
    )
