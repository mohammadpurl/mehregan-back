"""CRUD و هم‌ترازسازی سیاست‌های SLA با تعریف گردش‌کار."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.sla_policy import SlaPolicy
from app.models.workflow_definition import WorkflowDefinition
from app.schemas.sla_policy import SlaPolicyCreate, SlaPolicyUpdate
from app.services.workflow_definition_service import (
    DEFAULT_ROLE_STEPS,
    get_steps_config,
)
from app.services.workflow_step_config import normalize_steps_config

DEFAULT_SLA_MAX_MINUTES = 24 * 60  # 24 hours


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


def _ceo_role_id(db: Session) -> int | None:
    row = (
        db.query(Role)
        .filter(func.lower(Role.name).in_(("ceo", "managing_director", "مدیرعامل")))
        .first()
    )
    return row.id if row else None


def ensure_default_sla_policy(
    db: Session,
    *,
    ref_type: str,
    step_order: int,
    max_minutes: int = DEFAULT_SLA_MAX_MINUTES,
) -> SlaPolicy:
    """اگر سیاست نبود بساز؛ اگر غیرفعال بود فعال نکن (ادمین تصمیم گرفته)."""
    rt = (ref_type or "workflow").strip()
    existing = (
        db.query(SlaPolicy)
        .filter(SlaPolicy.ref_type == rt, SlaPolicy.step_order == step_order)
        .first()
    )
    if existing:
        return existing
    row = SlaPolicy(
        ref_type=rt,
        step_order=step_order,
        max_minutes=max_minutes,
        escalate_to_role_id=_ceo_role_id(db),
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _ref_types_and_step_counts(db: Session) -> dict[str, int]:
    """از تعریف‌های DB + defaults تعداد مراحل هر نوع را استخراج می‌کند."""
    counts: dict[str, int] = {}

    for ref_type in DEFAULT_ROLE_STEPS:
        steps = get_steps_config(db, ref_type)
        counts[ref_type] = max(len(steps), 1)

    defs = db.query(WorkflowDefinition).all()
    for row in defs:
        rt = (row.ref_type or "").strip()
        if not rt:
            continue
        if isinstance(row.steps_config, list) and row.steps_config:
            steps = normalize_steps_config(row.steps_config)
            counts[rt] = max(len(steps), counts.get(rt, 0), 1)
        elif rt not in counts:
            counts[rt] = 1

    return counts


def sync_sla_policies_from_definitions(
    db: Session,
    *,
    max_minutes: int = DEFAULT_SLA_MAX_MINUTES,
    commit: bool = True,
) -> int:
    """
    برای هر (ref_type, step_order) تعریف‌شده، سیاست SLA بسازد اگر نبود.
    سیاست‌های موجود را عوض نمی‌کند (ادمین override حفظ می‌شود).
    """
    ceo_role_id = _ceo_role_id(db)
    created = 0
    for ref_type, step_count in _ref_types_and_step_counts(db).items():
        for step_order in range(1, step_count + 1):
            exists = (
                db.query(SlaPolicy)
                .filter(
                    SlaPolicy.ref_type == ref_type,
                    SlaPolicy.step_order == step_order,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                SlaPolicy(
                    ref_type=ref_type,
                    step_order=step_order,
                    max_minutes=max_minutes,
                    escalate_to_role_id=ceo_role_id,
                    is_active=True,
                )
            )
            created += 1
    if commit and created:
        db.commit()
    elif commit:
        db.commit()
    return created
