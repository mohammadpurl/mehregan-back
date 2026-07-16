"""روال یکسان تأیید مالی + ثبت/تأیید سپیدار برای همه انواع درخواست مالی."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.constants.financial_workflow import (
    ACTION_APPROVAL,
    ACTION_MARK_PAYMENT,
    CONFIRM_SEPIDAR_ACTIONS,
    FINANCIAL_WORKFLOW_REF_TYPES,
)
from app.infrastructure.messaging.events import WORKFLOW_APPROVED, WORKFLOW_NEXT_STEP
from app.infrastructure.messaging.publisher import publish_event
from app.models.financial_document import FinancialDocument
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import mark_inbox_done_for_workflow
from app.services.workflow_approval_log import record_workflow_decision
from app.services.workflow_notifications import notify_workflow_next_step
from app.services.workflow_step_access import user_can_act_on_workflow_step
from app.services.workflow_step_config import get_step_config_at_order

_ACTIVE_STATUSES = ("pending", "in_progress", "active")


def is_financial_ref_type(ref_type: str | None) -> bool:
    return bool(ref_type) and ref_type in FINANCIAL_WORKFLOW_REF_TYPES


def step_action_for_order(db: Session, ref_type: str, order: int) -> str:
    cfg = get_step_config_at_order(db, ref_type, order)
    if not cfg:
        return ACTION_APPROVAL
    action = (cfg.get("step_action") or ACTION_APPROVAL).strip()
    return action or ACTION_APPROVAL


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


def _load_entity(db: Session, ref_type: str, ref_id: int):
    if ref_type in ("payment_request", "payment_order"):
        return db.get(PaymentRequest, ref_id)
    if ref_type == "petty_cash":
        return db.get(PettyCashRequest, ref_id)
    if ref_type == "financial_document":
        return db.get(FinancialDocument, ref_id)
    return None


def get_sepidar_registered_at(entity) -> datetime | None:
    if entity is None:
        return None
    # payment_request: payment_marked_* = ثبت کارشناس در سپیدار
    if hasattr(entity, "payment_marked_at") and entity.payment_marked_at:
        return entity.payment_marked_at
    return getattr(entity, "sepidar_registered_at", None)


def mark_sepidar_registered(entity, user: User) -> None:
    now = datetime.utcnow()
    if hasattr(entity, "payment_marked_at"):
        entity.payment_marked_at = now
        entity.payment_marked_by = user.id
    if hasattr(entity, "sepidar_registered_at"):
        entity.sepidar_registered_at = now
        entity.sepidar_registered_by = user.id


def mark_sepidar_confirmed(entity, user: User) -> None:
    now = datetime.utcnow()
    if hasattr(entity, "sepidar_confirmed_at"):
        entity.sepidar_confirmed_at = now
        entity.sepidar_confirmed_by = user.id
    # اسناد مالی: finance_confirmed_at را هم هم‌زمان ست کن
    if hasattr(entity, "finance_confirmed_at"):
        entity.finance_confirmed_at = now


def complete_mark_payment_step(
    db: Session,
    *,
    instance: WorkflowInstance,
    user: User,
    comment: str | None = None,
) -> None:
    if not is_financial_ref_type(instance.ref_type):
        raise ValueError("این گردش‌کار مالی نیست")
    if instance.status not in _ACTIVE_STATUSES:
        raise ValueError("گردش‌کار فعال یافت نشد")
    step = _pending_step(db, instance.id)
    if not step:
        raise ValueError("مرحله‌ای در انتظار نیست")
    action = step_action_for_order(db, instance.ref_type, step.order)
    if action != ACTION_MARK_PAYMENT:
        raise ValueError("این مرحله «ثبت در سپیدار» نیست")
    if not user_can_act_on_workflow_step(user, step):
        raise ValueError("دسترسی به این مرحله مجاز نیست")

    entity = _load_entity(db, instance.ref_type, int(instance.ref_id))
    if not entity:
        raise ValueError("درخواست مالی یافت نشد")

    mark_sepidar_registered(entity, user)
    _complete_step_record(
        db,
        step,
        user,
        comment=comment or "ثبت در سپیدار انجام شد",
    )
    mark_inbox_done_for_workflow(db, instance.id, user_id=user.id)
    db.flush()

    advance_workflow_after_step(
        db,
        instance_id=instance.id,
        completed_order=step.order,
        actor=user,
    )


def assert_can_approve_pending_step(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    *,
    payment_executed: bool = False,
    sepidar_confirmed: bool = False,
) -> None:
    if not is_financial_ref_type(instance.ref_type):
        return
    action = step_action_for_order(db, instance.ref_type, step.order)
    if action == ACTION_MARK_PAYMENT:
        raise ValueError(
            "ثبت در سپیدار از دکمه «ثبت در سپیدار انجام شد» انجام می‌شود، نه تأیید معمول کارتابل"
        )
    if action in CONFIRM_SEPIDAR_ACTIONS:
        entity = _load_entity(db, instance.ref_type, int(instance.ref_id))
        if not entity or not get_sepidar_registered_at(entity):
            raise ValueError(
                "ابتدا کارشناس مالی باید «ثبت در سپیدار انجام شد» را ثبت کند"
            )
        if not sepidar_confirmed:
            raise ValueError(
                "برای تأیید نهایی، تیک «در نرم‌افزار سپیدار ثبت شده است» الزامی است"
            )
    if payment_executed and action != ACTION_MARK_PAYMENT:
        raise ValueError("از دکمه ثبت در سپیدار استفاده کنید")


def try_complete_operational_from_inbox(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    user: User,
    *,
    payment_executed: bool = False,
) -> bool:
    if not is_financial_ref_type(instance.ref_type):
        return False
    if step_action_for_order(db, instance.ref_type, step.order) != ACTION_MARK_PAYMENT:
        return False
    if not payment_executed:
        return False
    complete_mark_payment_step(
        db,
        instance=instance,
        user=user,
        comment="ثبت در سپیدار انجام شد",
    )
    return True


def apply_sepidar_confirm_on_entity(
    db: Session,
    *,
    ref_type: str,
    ref_id: int,
    user: User,
) -> None:
    entity = _load_entity(db, ref_type, ref_id)
    if entity:
        mark_sepidar_confirmed(entity, user)


def advance_workflow_after_step(
    db: Session,
    *,
    instance_id: int,
    completed_order: int,
    actor: User,
) -> None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or not is_financial_ref_type(inst.ref_type):
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
            "ref_type": inst.ref_type,
            "ref_id": inst.ref_id,
            "user_id": actor.id,
        },
    )
