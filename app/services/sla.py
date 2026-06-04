from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.sla_record import SLARecord
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.sla_policy_service import get_sla_policy_for_step


def _current_pending_step(db: Session, instance_id: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter_by(instance_id=instance_id, status="pending")
        .order_by(WorkflowStep.order)
        .first()
    )


def is_current_pending_step(db: Session, step: WorkflowStep) -> bool:
    current = _current_pending_step(db, step.instance_id)
    return current is not None and current.id == step.id


def create_sla_for_workflow_step(
    db: Session,
    *,
    step: WorkflowStep,
    instance: WorkflowInstance,
) -> SLARecord | None:
    """Create SLA deadline for an active workflow step from sla_policies."""
    if not is_current_pending_step(db, step):
        return None

    policy = get_sla_policy_for_step(db, instance.ref_type, step.order)
    if not policy:
        return None

    existing = (
        db.query(SLARecord)
        .filter(
            SLARecord.step_id == step.id,
            SLARecord.is_triggered == False,  # noqa: E712
        )
        .first()
    )
    if existing:
        return existing

    record = SLARecord(
        step_id=step.id,
        ref_id=instance.id,
        ref_type=instance.ref_type or "workflow",
        due_at=datetime.utcnow() + timedelta(minutes=policy.max_minutes),
    )
    db.add(record)
    db.flush()
    return record


def close_sla_for_step(db: Session, step_id: int) -> None:
    """Mark SLA records for a completed step as triggered (no breach)."""
    (
        db.query(SLARecord)
        .filter(
            SLARecord.step_id == step_id,
            SLARecord.is_triggered == False,  # noqa: E712
        )
        .update({"is_triggered": True}, synchronize_session=False)
    )


def close_sla_for_instance(db: Session, instance_id: int) -> None:
    """Close all open SLA records when workflow ends or is rejected."""
    step_ids = [
        row[0]
        for row in db.query(WorkflowStep.id)
        .filter(WorkflowStep.instance_id == instance_id)
        .all()
    ]
    if not step_ids:
        return
    (
        db.query(SLARecord)
        .filter(
            SLARecord.step_id.in_(step_ids),
            SLARecord.is_triggered == False,  # noqa: E712
        )
        .update({"is_triggered": True}, synchronize_session=False)
    )


# Backward-compatible alias (legacy callers)
def create_sla_for_step(
    db: Session, step_id: int, ref_id: int, ref_type: str
) -> SLARecord | None:
    step = db.get(WorkflowStep, step_id)
    if not step:
        return None
    inst = db.get(WorkflowInstance, ref_id)
    if not inst:
        inst = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.ref_id == ref_id,
                WorkflowInstance.ref_type == ref_type,
            )
            .first()
        )
    if not inst:
        return None
    return create_sla_for_workflow_step(db, step=step, instance=inst)
