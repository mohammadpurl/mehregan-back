"""گردش‌کار یکپارچه درخواست خرید کالا (ref_type=purchase_request)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.constants.procurement import (
    REQUEST_TYPE_PURCHASE,
    STATUS_AWAITING_INVOICE,
    STATUS_AWAITING_PROFORMA,
    STATUS_PROFORMA_REVIEW,
    WORKFLOW_REF_PROFORMA,
    WORKFLOW_REF_PURCHASE,
    WORKFLOW_REF_REQUEST,
)
from app.infrastructure.messaging.events import WORKFLOW_APPROVED, WORKFLOW_NEXT_STEP
from app.infrastructure.messaging.publisher import publish_event
from app.models.request import Request
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import mark_inbox_done_for_workflow
from app.services.workflow_approval_log import record_workflow_decision
from app.services.workflow_definition_service import get_steps_config
from app.services.workflow_notifications import notify_workflow_next_step
from app.services.workflow_step_access import user_can_act_on_workflow_step
from app.services.workflow_step_config import get_step_config_at_order

ACTION_APPROVAL = "approval"
ACTION_UPLOAD_PROFORMA = "upload_proforma"
ACTION_APPROVE_PROFORMA = "approve_proforma"
ACTION_UPLOAD_INVOICE = "upload_invoice"
ACTION_CONFIRM_PAYMENT = "confirm_payment"

_PURCHASE_WORKFLOW_REFS = frozenset(
    {WORKFLOW_REF_PURCHASE, WORKFLOW_REF_REQUEST, WORKFLOW_REF_PROFORMA}
)

_ACTIVE_STATUSES = ("pending", "in_progress", "active")


def is_purchase_workflow_ref(ref_type: str | None) -> bool:
    return ref_type in _PURCHASE_WORKFLOW_REFS


def purchase_workflow_ref_types() -> tuple[str, ...]:
    return tuple(_PURCHASE_WORKFLOW_REFS)


def step_action_for_order(db: Session, ref_type: str, order: int) -> str:
    cfg = get_step_config_at_order(db, ref_type, order)
    if not cfg:
        return ACTION_APPROVAL
    action = (cfg.get("step_action") or cfg.get("stepAction") or ACTION_APPROVAL).strip()
    return action or ACTION_APPROVAL


def _latest_instance(db: Session, ref_type: str, request_id: int) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == request_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def get_active_purchase_workflow(
    db: Session, request_id: int
) -> WorkflowInstance | None:
    """نمونهٔ فعال گردش‌کار خرید — اول unified، سپس legacy."""
    for ref_type in (WORKFLOW_REF_PURCHASE, WORKFLOW_REF_REQUEST, WORKFLOW_REF_PROFORMA):
        inst = _latest_instance(db, ref_type, request_id)
        if inst and inst.status in _ACTIVE_STATUSES:
            return inst
    return None


def get_primary_purchase_workflow(
    db: Session, request_id: int
) -> WorkflowInstance | None:
    """آخرین نمونه برای نمایش پیشرفت (فعال یا تمام‌شده)."""
    inst = _latest_instance(db, WORKFLOW_REF_PURCHASE, request_id)
    if inst:
        return inst
    return _latest_instance(db, WORKFLOW_REF_REQUEST, request_id)


def _pending_step(db: Session, instance_id: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter_by(instance_id=instance_id, status="pending")
        .order_by(WorkflowStep.order)
        .first()
    )


def _resolve_user(db: Session, user_or_id: User | int) -> User:
    if isinstance(user_or_id, User):
        return user_or_id
    row = db.get(User, int(user_or_id))
    if not row:
        raise ValueError("کاربر یافت نشد")
    return row


def _complete_step_record(
    db: Session,
    step: WorkflowStep,
    user: User,
    *,
    comment: str | None = None,
) -> None:
    from datetime import datetime

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


def _notify_next_step(db: Session, instance: WorkflowInstance, step: WorkflowStep) -> None:
    payload = {
        "instance_id": instance.id,
        "role_id": step.role_id,
        "step_id": step.id,
        "user_id": step.assigned_user_id,
        "ref_type": instance.ref_type,
        "ref_id": instance.ref_id,
    }
    publish_event(WORKFLOW_NEXT_STEP, payload)
    notify_workflow_next_step(db, payload)


def _on_purchase_step_completed(
    db: Session,
    instance: WorkflowInstance,
    completed_order: int,
    *,
    payment_method: str | None = None,
    payment_comment: str | None = None,
) -> None:
    if instance.ref_type != WORKFLOW_REF_PURCHASE:
        return
    request_id = int(instance.ref_id)
    if completed_order == 2:
        from app.services.procurement.purchase_request_service import (
            mark_request_phase1_approved,
        )

        mark_request_phase1_approved(db, request_id)
    elif completed_order == 4:
        from app.services.procurement.proforma_service import mark_proforma_workflow_approved

        mark_proforma_workflow_approved(
            db,
            request_id,
            None,
            payment_method=payment_method,
            payment_comment=payment_comment,
        )
    elif completed_order == 5:
        from app.services.procurement.procurement_notifications import (
            notify_finance_invoice_uploaded,
        )

        notify_finance_invoice_uploaded(db, request_id)


def advance_workflow_after_step(
    db: Session,
    instance_id: int,
    *,
    completed_order: int,
    actor: User,
    payment_method: str | None = None,
    payment_comment: str | None = None,
) -> None:
    """پس از تکمیل یک مرحله، وضعیت درخواست و مرحله بعد را هماهنگ می‌کند."""
    instance = db.get(WorkflowInstance, instance_id)
    if not instance:
        return

    _on_purchase_step_completed(
        db,
        instance,
        completed_order,
        payment_method=payment_method,
        payment_comment=payment_comment,
    )

    while True:
        next_step = _pending_step(db, instance_id)
        if not next_step:
            instance.status = "approved"
            db.commit()
            approved_payload = {
                "instance_id": instance_id,
                "user_id": actor.id,
                "ref_type": instance.ref_type,
                "ref_id": instance.ref_id,
                "payment_method": payment_method,
                "comment": payment_comment,
            }
            publish_event(WORKFLOW_APPROVED, approved_payload)
            from app.services.workflow_procurement_bridge import on_pr_approved

            on_pr_approved(db, approved_payload)
            return

        _notify_next_step(db, instance, next_step)
        db.commit()
        return


def complete_operational_step(
    db: Session,
    *,
    request_id: int,
    user_or_id: User | int,
    expected_action: str,
    comment: str | None = None,
) -> None:
    """تکمیل مراحل عملیاتی (پیش‌فاکتور / فاکتور / پرداخت) بدون تأیید از کارتابل."""
    user = _resolve_user(db, user_or_id)
    inst = get_active_purchase_workflow(db, request_id)
    if not inst or inst.ref_type != WORKFLOW_REF_PURCHASE:
        raise ValueError("گردش‌کار یکپارچه خرید برای این درخواست فعال نیست")

    step = _pending_step(db, inst.id)
    if not step:
        raise ValueError("مرحلهٔ جاری یافت نشد")

    action = step_action_for_order(db, inst.ref_type, step.order)
    if action != expected_action:
        raise ValueError("این اقدام با مرحلهٔ جاری گردش‌کار هم‌خوان نیست")

    if not user_can_act_on_workflow_step(user, step):
        raise ValueError("شما مجاز به انجام این مرحله نیستید")

    if expected_action == ACTION_UPLOAD_PROFORMA:
        from app.constants.procurement import PROFORMA_STATUS_SUBMITTED
        from app.models.procurement.proforma import ProcurementProforma

        row = (
            db.query(ProcurementProforma)
            .filter(
                ProcurementProforma.request_id == request_id,
                ProcurementProforma.status == PROFORMA_STATUS_SUBMITTED,
            )
            .order_by(ProcurementProforma.id.desc())
            .first()
        )
        if not row:
            raise ValueError("ابتدا پیش‌فاکتور را ثبت و «ارسال برای تأیید» کنید")
    elif expected_action == ACTION_UPLOAD_INVOICE:
        from app.services.attachment_service import (
            ENTITY_PROCUREMENT_INVOICE,
            list_attachments_serialized,
        )

        if not list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id):
            raise ValueError("ابتدا فایل فاکتور را بارگذاری کنید")

    _complete_step_record(db, step, user, comment=comment)
    mark_inbox_done_for_workflow(db, inst.id, user_id=user.id)
    db.flush()

    req = db.get(Request, request_id)
    if req and req.type == REQUEST_TYPE_PURCHASE:
        if expected_action == ACTION_UPLOAD_PROFORMA and req.status == STATUS_AWAITING_PROFORMA:
            req.status = STATUS_PROFORMA_REVIEW
        elif expected_action == ACTION_CONFIRM_PAYMENT:
            from datetime import datetime

            from app.constants.procurement import STATUS_COMPLETED

            req.invoice_paid_at = datetime.utcnow()
            req.invoice_paid_by = user.id
            req.status = STATUS_COMPLETED

    advance_workflow_after_step(
        db,
        inst.id,
        completed_order=step.order,
        actor=user,
    )


def _has_submitted_proforma(db: Session, request_id: int) -> bool:
    from app.constants.procurement import PROFORMA_STATUS_SUBMITTED
    from app.models.procurement.proforma import ProcurementProforma

    return (
        db.query(ProcurementProforma.id)
        .filter(
            ProcurementProforma.request_id == request_id,
            ProcurementProforma.status == PROFORMA_STATUS_SUBMITTED,
        )
        .first()
        is not None
    )


def repair_stuck_purchase_operational_steps(db: Session, request_id: int) -> bool:
    """اگر پیش‌فاکتور/فاکتور ثبت شده ولی مرحله عملیاتی هنوز pending است، جبران می‌کند."""
    inst = get_active_purchase_workflow(db, request_id)
    if not inst or inst.ref_type != WORKFLOW_REF_PURCHASE:
        return False
    step = _pending_step(db, inst.id)
    if not step or not step.assigned_user_id:
        return False
    action = step_action_for_order(db, inst.ref_type, step.order)
    assignee = db.get(User, step.assigned_user_id)
    if not assignee:
        return False

    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        return False

    try:
        if action == ACTION_UPLOAD_PROFORMA and _has_submitted_proforma(db, request_id):
            complete_operational_step(
                db,
                request_id=request_id,
                user_or_id=assignee,
                expected_action=ACTION_UPLOAD_PROFORMA,
            )
            return True
        if action == ACTION_UPLOAD_INVOICE:
            from app.services.attachment_service import (
                ENTITY_PROCUREMENT_INVOICE,
                list_attachments_serialized,
            )

            if list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id):
                complete_operational_step(
                    db,
                    request_id=request_id,
                    user_or_id=assignee,
                    expected_action=ACTION_UPLOAD_INVOICE,
                )
                return True
    except ValueError:
        return False
    return False


def try_complete_operational_from_inbox(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    user: User,
) -> bool:
    """اگر شرایط عملیاتی برقرار است، مرحله را تکمیل و گردش‌کار را جلو می‌برد."""
    if instance.ref_type != WORKFLOW_REF_PURCHASE:
        return False
    action = step_action_for_order(db, instance.ref_type, step.order)
    if action not in (ACTION_UPLOAD_PROFORMA, ACTION_UPLOAD_INVOICE):
        return False

    request_id = int(instance.ref_id)
    if action == ACTION_UPLOAD_PROFORMA and not _has_submitted_proforma(db, request_id):
        return False

    actor = db.get(User, step.assigned_user_id) if step.assigned_user_id else user
    if not actor:
        actor = user
    complete_operational_step(
        db,
        request_id=request_id,
        user_or_id=actor,
        expected_action=action,
    )
    return True


def assert_can_approve_pending_step(
    db: Session,
    instance: WorkflowInstance,
    step: WorkflowStep,
    *,
    payment_method: str | None = None,
) -> None:
    """جلوگیری از تأیید کارتابلی برای مراحل عملیاتی."""
    if instance.ref_type != WORKFLOW_REF_PURCHASE:
        return
    action = step_action_for_order(db, instance.ref_type, step.order)
    if action == ACTION_UPLOAD_PROFORMA:
        if _has_submitted_proforma(db, int(instance.ref_id)):
            raise ValueError(
                "پیش‌فاکتور ارسال شده است؛ گردش‌کار در حال به‌روزرسانی است. "
                "صفحه را رفرش کنید یا چند ثانیه بعد دوباره کارتابل را باز کنید."
            )
        raise ValueError(
            "ثبت و «ارسال برای تأیید» پیش‌فاکتور از صفحه «درخواست‌های خرید» انجام می‌شود، نه از کارتابل."
        )
    if action == ACTION_UPLOAD_INVOICE:
        raise ValueError("بارگذاری فاکتور از صفحه درخواست خرید انجام می‌شود")
    if action == ACTION_APPROVE_PROFORMA:
        if not payment_method or not str(payment_method).strip():
            raise ValueError("روش پرداخت هنگام تأیید پیش‌فاکتور الزامی است")
    if action == ACTION_CONFIRM_PAYMENT:
        from app.services.attachment_service import (
            ENTITY_PROCUREMENT_INVOICE,
            list_attachments_serialized,
        )

        if not list_attachments_serialized(
            db, ENTITY_PROCUREMENT_INVOICE, int(instance.ref_id)
        ):
            raise ValueError("ابتدا باید فاکتور توسط مسئول خرید بارگذاری شود")
