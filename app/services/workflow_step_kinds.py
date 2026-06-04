"""تشخیص نوع مرحله workflow (مدیریتی در مقابل مالی)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_step_config import get_step_config_at_order

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


def _step_config(db: Session, inst: WorkflowInstance, step: WorkflowStep) -> dict | None:
    return get_step_config_at_order(db, inst.ref_type, step.order)


def step_is_financial(db: Session, inst: WorkflowInstance, step: WorkflowStep) -> bool:
    cfg = _step_config(db, inst, step)
    if not cfg:
        return False
    strategy = (cfg.get("assignee_strategy") or "").strip().lower()
    if strategy in ("submitter_manager", "department_head"):
        return False
    aliases = {str(a).strip().lower() for a in (cfg.get("role_aliases") or [])}
    return bool(aliases & FINANCE_ROLE_ALIASES)


def step_is_manager_review(db: Session, inst: WorkflowInstance, step: WorkflowStep) -> bool:
    cfg = _step_config(db, inst, step)
    if not cfg:
        return step.order == 1
    strategy = (cfg.get("assignee_strategy") or "").strip().lower()
    if strategy in ("submitter_manager", "department_head"):
        return True
    aliases = {str(a).strip().lower() for a in (cfg.get("role_aliases") or [])}
    if aliases & MANAGER_ROLE_ALIASES and not (aliases & FINANCE_ROLE_ALIASES):
        return True
    return strategy == "submitter_manager"
