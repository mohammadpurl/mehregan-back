"""قوانین auto-skip مراحل تأیید پشت‌سرهم با همان تأییدکننده."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_step_access import is_same_approver_for_auto_skip
from app.services.workflow_step_config import get_step_config_at_order

# مراحلی که نیازمند اقدام/دادهٔ جدا هستند — هرگز auto-skip نمی‌شوند
_NON_SKIPPABLE_ACTIONS = frozenset(
    {
        "mark_payment",
        "confirm_sepidar",
        "final_payment_approval",
        "upload_proforma",
        "approve_proforma",
        "upload_invoice",
        "confirm_payment",
        "fill_stock",
        "upload_bol",
        "confirm_receipt",
        "confirm_warehouse_sepidar",
    }
)


def _step_action(db: Session, ref_type: str, order: int) -> str:
    cfg = get_step_config_at_order(db, ref_type, order)
    if not cfg:
        return "approval"
    action = (cfg.get("step_action") or cfg.get("stepAction") or "approval").strip()
    return action or "approval"


def next_step_requires_data_input(
    db: Session,
    instance: WorkflowInstance,
    next_step: WorkflowStep,
) -> bool:
    """
    آیا مرحلهٔ بعدی طوری است که باید داده بین تأییدها وارد/تغییر کند؟
    (شرایط وام/مساعده/حساب مبدأ، یا اقدام عملیاتی)
    """
    action = _step_action(db, instance.ref_type, next_step.order)
    if action in _NON_SKIPPABLE_ACTIONS:
        return True

    if instance.ref_type not in (
        "payment_request",
        "payment_order",
    ):
        return False

    from app.models.payment_request import PaymentRequest
    from app.services.payment_request_terms import (
        financial_terms_satisfied,
        must_collect_financial_terms,
    )

    pr = db.get(PaymentRequest, instance.ref_id)
    if not pr:
        return False
    if financial_terms_satisfied(pr):
        return False
    return must_collect_financial_terms(db, instance, pr, next_step)


def can_auto_skip_next_approval_step(
    db: Session,
    instance: WorkflowInstance | None,
    actor: User,
    next_step: WorkflowStep,
) -> bool:
    """
    یک تأیید کافی است اگر:
    - مسئول مرحلهٔ بعد همان تأییدکننده باشد
    - مرحله تأیید ساده باشد (نه عملیاتی)
    - بین مراحل نیاز به ورود/تغییر داده نباشد
    """
    if not instance:
        return False
    if not is_same_approver_for_auto_skip(actor, next_step):
        return False

    cfg = get_step_config_at_order(db, instance.ref_type, next_step.order)
    if cfg is not None and cfg.get("allow_auto_skip") is False:
        return False

    action = _step_action(db, instance.ref_type, next_step.order)
    if action in _NON_SKIPPABLE_ACTIONS:
        return False
    if action != "approval":
        return False

    if next_step_requires_data_input(db, instance, next_step):
        return False

    return True
