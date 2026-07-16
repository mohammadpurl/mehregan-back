"""سازگاری با کد قدیمی — منطق اصلی در financial_workflow است."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.constants.payment_order import WORKFLOW_REF_PAYMENT_ORDER
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services import financial_workflow as fw


def step_action_for_order(db: Session, order: int) -> str:
    return fw.step_action_for_order(db, WORKFLOW_REF_PAYMENT_ORDER, order)


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


def complete_mark_payment_step(
    db: Session,
    *,
    payment_request_id: int,
    user: User,
    comment: str | None = None,
) -> None:
    inst = workflow_instance_for_payment_order(db, payment_request_id)
    if not inst:
        raise ValueError("گردش‌کار فعال یافت نشد")
    fw.complete_mark_payment_step(db, instance=inst, user=user, comment=comment)


def assert_can_approve_pending_step(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    *,
    payment_executed: bool = False,
    sepidar_confirmed: bool = False,
) -> None:
    fw.assert_can_approve_pending_step(
        db,
        instance,
        step,
        payment_executed=payment_executed,
        sepidar_confirmed=sepidar_confirmed,
    )


def try_complete_operational_from_inbox(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    user: User,
    *,
    payment_executed: bool = False,
) -> bool:
    return fw.try_complete_operational_from_inbox(
        db, instance, step, user, payment_executed=payment_executed
    )


def advance_workflow_after_step(
    db: Session,
    *,
    instance_id: int,
    completed_order: int,
    actor: User,
) -> None:
    fw.advance_workflow_after_step(
        db,
        instance_id=instance_id,
        completed_order=completed_order,
        actor=actor,
    )
