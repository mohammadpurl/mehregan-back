from datetime import date, datetime

from sqlalchemy.orm import Session

from app.infrastructure.messaging.events import (
    WORKFLOW_APPROVED,
    WORKFLOW_NEXT_STEP,
    WORKFLOW_REJECTED,
)
from app.infrastructure.messaging.publisher import publish_event
from app.models import WorkflowInstance, WorkflowStep
from app.services.assignment import resolve_assignee_for_role
from app.services.inbox import mark_inbox_done_for_workflow
from app.models.payment_request import PaymentRequest
from app.services.payment_request_terms import (
    ApproverTermsPayload,
    apply_approver_terms_before_approve,
    financial_terms_satisfied,
)
from app.services.workflow_step_kinds import step_is_financial
from app.services.workflow_approval_log import record_workflow_decision
from app.services.workflow_step_access import user_can_act_on_workflow_step
from app.services.workflow_notifications import notify_workflow_next_step
from app.models.user import User

ALLOWED_TRANSITIONS = {
    "draft": ["pending"],
    "pending": ["approved", "rejected"],
    "approved": [],
    "rejected": [],
}

AUTO_SKIP_COMMENT = "تأیید خودکار: همان تأییدکننده مرحله قبل"


def _pending_step(db: Session, instance_id: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter_by(instance_id=instance_id, status="pending")
        .order_by(WorkflowStep.order)
        .first()
    )


def _assert_can_approve(step: WorkflowStep, user) -> None:
    if not user_can_act_on_workflow_step(user, step):
        raise ValueError("access denied")


def _complete_step(
    db: Session,
    step: WorkflowStep,
    user,
    *,
    auto_skipped: bool = False,
    comment: str | None = None,
) -> None:
    from app.services.sla import close_sla_for_step

    step.status = "approved"
    step.approved_by = user.id
    step.approved_at = datetime.utcnow()
    close_sla_for_step(db, step.id)
    decision_comment = AUTO_SKIP_COMMENT if auto_skipped else (comment or None)
    record_workflow_decision(
        db,
        instance_id=step.instance_id,
        step_id=step.id,
        approved_by=user.id,
        decision="approved",
        comment=decision_comment,
    )


def approve_step(
    db: Session,
    instance_id: int,
    user,
    *,
    comment: str | None = None,
    amount: float | None = None,
    payment_date: date | None = None,
    installment_count: int | None = None,
    first_installment_date: date | None = None,
    settlement_date: date | None = None,
    payer_company_account_id: int | None = None,
    payer_account: str | None = None,
    payment_method: str | None = None,
    payment_executed: bool = False,
    sepidar_confirmed: bool = False,
):
    terms = None
    if (
        amount is not None
        or payment_date is not None
        or installment_count is not None
        or first_installment_date is not None
        or settlement_date is not None
        or payer_company_account_id is not None
        or payer_account is not None
        or payment_method is not None
    ):
        terms = ApproverTermsPayload(
            amount=amount,
            payment_date=payment_date,
            installment_count=installment_count,
            first_installment_date=first_installment_date,
            settlement_date=settlement_date,
            payer_company_account_id=payer_company_account_id,
            payer_account=payer_account,
            payment_method=payment_method,
        )

    apply_approver_terms_before_approve(db, instance_id, user, terms)

    step = _pending_step(db, instance_id)
    if not step:
        raise ValueError("no pending step")

    instance = db.get(WorkflowInstance, instance_id)

    from app.constants.procurement import WORKFLOW_REF_PURCHASE
    from app.services.procurement.purchase_workflow import (
        advance_workflow_after_step,
        assert_can_approve_pending_step,
        step_action_for_order,
        try_complete_operational_from_inbox,
    )

    from app.services.financial_workflow import (
        advance_workflow_after_step as fin_advance_workflow_after_step,
        apply_sepidar_confirm_on_entity,
        assert_can_approve_pending_step as fin_assert_can_approve,
        is_financial_ref_type,
        step_action_for_order as fin_step_action_for_order,
        try_complete_operational_from_inbox as fin_try_complete_operational,
    )
    from app.constants.financial_workflow import CONFIRM_SEPIDAR_ACTIONS

    if instance and instance.ref_type == WORKFLOW_REF_PURCHASE:
        if try_complete_operational_from_inbox(db, instance, step, user):
            return
        assert_can_approve_pending_step(
            db, instance, step, payment_method=payment_method
        )

    if instance and is_financial_ref_type(instance.ref_type):
        if fin_try_complete_operational(
            db, instance, step, user, payment_executed=payment_executed
        ):
            return
        fin_assert_can_approve(
            db,
            instance,
            step,
            payment_executed=payment_executed,
            sepidar_confirmed=sepidar_confirmed,
        )

    completed_action = (
        fin_step_action_for_order(db, instance.ref_type, step.order)
        if instance and is_financial_ref_type(instance.ref_type)
        else None
    )

    _assert_can_approve(step, user)
    _complete_step(db, step, user, auto_skipped=False, comment=comment)
    mark_inbox_done_for_workflow(db, instance_id, user_id=user.id)

    if (
        instance
        and is_financial_ref_type(instance.ref_type)
        and completed_action in CONFIRM_SEPIDAR_ACTIONS
    ):
        apply_sepidar_confirm_on_entity(
            db,
            ref_type=instance.ref_type,
            ref_id=int(instance.ref_id),
            user=user,
        )

    if instance and instance.ref_type == "procurement_proforma":
        if not payment_method or not str(payment_method).strip():
            raise ValueError("روش پرداخت هنگام تأیید پیش‌فاکتور الزامی است")

    if instance and instance.ref_type == WORKFLOW_REF_PURCHASE:
        completed_order = step.order
        advance_workflow_after_step(
            db,
            instance_id,
            completed_order=completed_order,
            actor=user,
            payment_method=payment_method,
            payment_comment=comment,
        )
        return

    if instance and is_financial_ref_type(instance.ref_type):
        fin_advance_workflow_after_step(
            db,
            instance_id=instance_id,
            completed_order=step.order,
            actor=user,
        )
        return

    while True:
        next_step = _pending_step(db, instance_id)
        if not next_step:
            if instance:
                instance.status = "approved"
            db.commit()
            approved_payload: dict = {
                "instance_id": instance_id,
                "user_id": user.id,
                "comment": comment,
                "payment_method": payment_method,
            }
            if instance:
                approved_payload["ref_type"] = instance.ref_type
                approved_payload["ref_id"] = instance.ref_id
            publish_event(WORKFLOW_APPROVED, approved_payload)
            from app.services.workflow_procurement_bridge import on_pr_approved

            on_pr_approved(db, approved_payload)
            return

        assigned_user = None
        if next_step.assigned_user_id:
            assigned_user = db.get(User, next_step.assigned_user_id)
            if assigned_user and not assigned_user.is_active:
                assigned_user = None
        if assigned_user is None:
            assigned_user = resolve_assignee_for_role(
                db, next_step.role_id, next_step.assigned_user_id
            )
        if assigned_user:
            next_step.assigned_user_id = assigned_user.id

        if user_can_act_on_workflow_step(user, next_step):
            if (
                instance
                and instance.ref_type in ("payment_request", "payment_order")
                and step_is_financial(db, instance, next_step)
            ):
                pr = db.get(PaymentRequest, instance.ref_id)
                if not pr or not financial_terms_satisfied(pr):
                    db.commit()
                    next_payload = {
                        "instance_id": instance_id,
                        "role_id": next_step.role_id,
                        "step_id": next_step.id,
                        "user_id": next_step.assigned_user_id,
                    }
                    db.commit()
                    publish_event(WORKFLOW_NEXT_STEP, next_payload)
                    notify_workflow_next_step(db, next_payload)
                    db.commit()
                    return
            _complete_step(db, next_step, user, auto_skipped=True)
            mark_inbox_done_for_workflow(db, instance_id, user_id=user.id)
            db.flush()
            continue

        next_payload = {
            "instance_id": instance_id,
            "role_id": next_step.role_id,
            "step_id": next_step.id,
            "user_id": next_step.assigned_user_id,
        }
        db.commit()
        publish_event(WORKFLOW_NEXT_STEP, next_payload)
        notify_workflow_next_step(db, next_payload)
        db.commit()
        return


def reject_step(
    db: Session,
    instance_id: int,
    user,
    *,
    comment: str | None = None,
    return_to: str = "previous",
):
    from app.services.workflow_reject import reject_step as _reject_with_return

    return _reject_with_return(
        db,
        instance_id,
        user,
        comment=comment,
        return_to=return_to,
    )


def can_transition(current_state: str, next_state: str) -> bool:
    return next_state in ALLOWED_TRANSITIONS.get(current_state, [])
