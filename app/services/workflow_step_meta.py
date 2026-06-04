"""شناسایی نوع مرحله workflow (مدیریتی / مالی)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_step_config import get_step_config_at_order
from app.services.workflow_step_access import user_can_act_on_workflow_step

FINANCE_ROLE_ALIASES = frozenset(
    {
        "finance_manager",
        "accountant",
        "مدیر مالی",
        "admin",
        "system_admin",
        "مدیر سیستم",
    }
)

MANAGER_ROLE_ALIASES = frozenset(
    {
        "manager",
        "project_manager",
        "مدیر پروژه",
        "مدیرعامل",
        "ceo",
        "managing_director",
        "مدیر مستقیم",
    }
)


def _step_config(db: Session, ref_type: str, order: int) -> dict | None:
    return get_step_config_at_order(db, ref_type, order)


def step_is_financial(db: Session, ref_type: str, order: int) -> bool:
    cfg = _step_config(db, ref_type, order)
    if not cfg:
        return False
    strategy = (cfg.get("assignee_strategy") or "").strip().lower()
    if strategy == "role_pool":
        aliases = {str(a).strip().lower() for a in cfg.get("role_aliases") or []}
        return bool(aliases & FINANCE_ROLE_ALIASES)
    aliases = {str(a).strip().lower() for a in cfg.get("role_aliases") or []}
    if aliases & FINANCE_ROLE_ALIASES and not aliases <= MANAGER_ROLE_ALIASES:
        return True
    label = (cfg.get("label") or "").strip()
    return "مالی" in label


def step_is_financial_for_instance(db: Session, inst: WorkflowInstance, step: WorkflowStep) -> bool:
    return step_is_financial(db, inst.ref_type, step.order)


def next_pending_step(db: Session, instance_id: int, after_order: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.instance_id == instance_id,
            WorkflowStep.status == "pending",
            WorkflowStep.order > after_order,
        )
        .order_by(WorkflowStep.order)
        .first()
    )


def user_must_provide_financial_terms_now(
    db: Session,
    inst: WorkflowInstance,
    user,
    pending_step: WorkflowStep,
) -> bool:
    """آیا در همین کلیک تأیید باید اقساط/حساب شرکت هم ارسال شود؟"""
    if step_is_financial_for_instance(db, inst, pending_step):
        return True
    nxt = next_pending_step(db, inst.id, pending_step.order)
    if not nxt:
        return False
    if not step_is_financial_for_instance(db, inst, nxt):
        return False
    return user_can_act_on_workflow_step(user, nxt)
