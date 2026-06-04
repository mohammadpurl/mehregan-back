from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sla_policy import SlaPolicy
from app.schemas.sla_policy import SlaPolicyCreate, SlaPolicyUpdate


def create_sla_policy(db: Session, payload: SlaPolicyCreate) -> SlaPolicy:
    existing = (
        db.query(SlaPolicy)
        .filter(
            SlaPolicy.ref_type == payload.ref_type,
            SlaPolicy.step_order == payload.step_order,
        )
        .first()
    )
    if existing:
        raise ValueError(
            f"SLA برای {payload.ref_type} مرحله {payload.step_order} از قبل وجود دارد"
        )
    row = SlaPolicy(
        ref_type=payload.ref_type.strip(),
        step_order=payload.step_order,
        max_minutes=payload.max_minutes,
        escalate_to_role_id=payload.escalate_to_role_id,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_sla_policy(
    db: Session, policy_id: int, payload: SlaPolicyUpdate
) -> SlaPolicy | None:
    row = db.get(SlaPolicy, policy_id)
    if not row:
        return None
    if payload.max_minutes is not None:
        row.max_minutes = payload.max_minutes
    if payload.escalate_to_role_id is not None:
        row.escalate_to_role_id = payload.escalate_to_role_id or None
    if payload.is_active is not None:
        row.is_active = payload.is_active
    db.commit()
    db.refresh(row)
    return row


def list_sla_policies(db: Session, ref_type: str | None = None) -> list[SlaPolicy]:
    query = db.query(SlaPolicy).order_by(SlaPolicy.ref_type, SlaPolicy.step_order)
    if ref_type:
        query = query.filter(SlaPolicy.ref_type == ref_type)
    return query.all()


def get_sla_policy_for_step(
    db: Session, ref_type: str, step_order: int
) -> SlaPolicy | None:
    return (
        db.query(SlaPolicy)
        .filter(
            SlaPolicy.ref_type == ref_type,
            SlaPolicy.step_order == step_order,
            SlaPolicy.is_active == True,  # noqa: E712
        )
        .first()
    )


def delete_sla_policy(db: Session, policy_id: int) -> bool:
    row = db.get(SlaPolicy, policy_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
