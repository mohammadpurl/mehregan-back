"""گردش‌کار یکپارچه درخواست خرید کالا (ref_type=purchase_request)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.procurement import (
    REQUEST_TYPE_PURCHASE,
    STATUS_AWAITING_BOL,
    STATUS_AWAITING_INVOICE,
    STATUS_AWAITING_PAYMENT_EXECUTION,
    STATUS_AWAITING_PROFORMA,
    STATUS_AWAITING_RECEIPT,
    STATUS_AWAITING_STOCK,
    STATUS_AWAITING_WAREHOUSE_POST,
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_PROFORMA_REVIEW,
    WORKFLOW_REF_PROFORMA,
    WORKFLOW_REF_PURCHASE,
    WORKFLOW_REF_REQUEST,
)
from app.constants.purchase_workflow_steps import (
    ACTION_APPROVAL,
    ACTION_APPROVE_PROFORMA,
    ACTION_CONFIRM_RECEIPT,
    ACTION_CONFIRM_WAREHOUSE_SEPIDAR,
    ACTION_FILL_STOCK,
    ACTION_MARK_PAYMENT,
    ACTION_UPLOAD_BOL,
    ACTION_UPLOAD_INVOICE,
    ACTION_UPLOAD_PROFORMA,
    PAYMENT_LOCATION_BANK,
    PAYMENT_LOCATION_PETTY_CASH,
    PAYMENT_LOCATIONS,
    PAYMENT_METHOD_CASH,
    PAYMENT_METHOD_CHECK,
    PURCHASE_PAYMENT_METHODS,
)
from app.infrastructure.messaging.events import WORKFLOW_APPROVED, WORKFLOW_NEXT_STEP
from app.infrastructure.messaging.publisher import publish_event
from app.models.request import Request
from app.models.request_item import RequestItem
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import mark_inbox_done_for_workflow
from app.services.workflow_approval_log import record_workflow_decision
from app.services.workflow_auto_skip import can_auto_skip_next_approval_step
from app.services.workflow_notifications import notify_workflow_next_step
from app.services.workflow_step_access import (
    AUTO_SKIP_COMMENT,
    user_can_act_on_workflow_step,
)
from app.services.workflow_step_config import get_step_config_at_order

# سازگاری با importهای قدیمی
ACTION_CONFIRM_PAYMENT = "confirm_payment"

_PURCHASE_WORKFLOW_REFS = frozenset(
    {WORKFLOW_REF_PURCHASE, WORKFLOW_REF_REQUEST, WORKFLOW_REF_PROFORMA}
)
_ACTIVE_STATUSES = ("pending", "in_progress", "active")
_OPERATIONAL_ACTIONS = frozenset(
    {
        ACTION_FILL_STOCK,
        ACTION_UPLOAD_PROFORMA,
        ACTION_UPLOAD_INVOICE,
        ACTION_MARK_PAYMENT,
        ACTION_UPLOAD_BOL,
        ACTION_CONFIRM_RECEIPT,
        ACTION_CONFIRM_WAREHOUSE_SEPIDAR,
    }
)


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
    for ref_type in (WORKFLOW_REF_PURCHASE, WORKFLOW_REF_REQUEST, WORKFLOW_REF_PROFORMA):
        inst = _latest_instance(db, ref_type, request_id)
        if inst and inst.status in _ACTIVE_STATUSES:
            return inst
    return None


def get_primary_purchase_workflow(
    db: Session, request_id: int
) -> WorkflowInstance | None:
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


def current_step_action(db: Session, request_id: int) -> str | None:
    inst = get_active_purchase_workflow(db, request_id)
    if not inst:
        return None
    step = _pending_step(db, inst.id)
    if not step:
        return None
    return step_action_for_order(db, inst.ref_type, step.order)


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


def _set_request_status(db: Session, request_id: int, status: str) -> None:
    req = db.get(Request, request_id)
    if req and req.type == REQUEST_TYPE_PURCHASE:
        req.status = status


def _on_purchase_step_completed(
    db: Session,
    instance: WorkflowInstance,
    completed_order: int,
    *,
    payment_method: str | None = None,
    payment_comment: str | None = None,
    payment_location: str | None = None,
    check_plan: list | None = None,
) -> None:
    if instance.ref_type != WORKFLOW_REF_PURCHASE:
        return
    request_id = int(instance.ref_id)
    action = step_action_for_order(db, instance.ref_type, completed_order)

    if action == ACTION_FILL_STOCK:
        _set_request_status(db, request_id, STATUS_PENDING)
    elif action == ACTION_APPROVAL and completed_order == 2:
        _set_request_status(db, request_id, STATUS_AWAITING_PROFORMA)
    elif action == ACTION_UPLOAD_PROFORMA:
        _set_request_status(db, request_id, STATUS_PROFORMA_REVIEW)
    elif action == ACTION_APPROVE_PROFORMA:
        from app.services.procurement.proforma_service import mark_proforma_workflow_approved

        mark_proforma_workflow_approved(
            db,
            request_id,
            None,
            payment_method=payment_method,
            payment_comment=payment_comment,
            payment_location=payment_location,
            check_plan=check_plan,
        )
        _set_request_status(db, request_id, STATUS_AWAITING_INVOICE)
    elif action == ACTION_UPLOAD_INVOICE:
        from app.services.procurement.procurement_notifications import (
            notify_finance_invoice_uploaded,
        )

        notify_finance_invoice_uploaded(db, request_id)
        _set_request_status(db, request_id, STATUS_AWAITING_PAYMENT_EXECUTION)
    elif action == ACTION_MARK_PAYMENT:
        req = db.get(Request, request_id)
        if req:
            req.invoice_paid_at = datetime.utcnow()
            req.sepidar_registered_at = datetime.utcnow()
        _set_request_status(db, request_id, STATUS_AWAITING_BOL)
    elif action == ACTION_UPLOAD_BOL:
        req = db.get(Request, request_id)
        if req:
            req.bol_uploaded_at = datetime.utcnow()
        _set_request_status(db, request_id, STATUS_AWAITING_RECEIPT)
    elif action == ACTION_CONFIRM_RECEIPT:
        req = db.get(Request, request_id)
        if req:
            req.goods_received_at = datetime.utcnow()
        _set_request_status(db, request_id, STATUS_AWAITING_WAREHOUSE_POST)
    elif action == ACTION_CONFIRM_WAREHOUSE_SEPIDAR:
        _post_stock_to_warehouse(db, request_id)
        req = db.get(Request, request_id)
        if req:
            req.sepidar_confirmed_at = datetime.utcnow()
            req.warehouse_posted_at = datetime.utcnow()
            req.status = STATUS_COMPLETED


def _post_stock_to_warehouse(db: Session, request_id: int) -> None:
    """ورود اقلام خرید به انبار مقصد."""
    from app.services.inventory.transaction import _apply_stock_in

    req = db.get(Request, request_id)
    if not req or not req.warehouse_id:
        raise ValueError("انبار مقصد برای ورود کالا مشخص نیست")
    lines = (
        db.query(RequestItem)
        .filter(RequestItem.request_id == request_id)
        .order_by(RequestItem.id)
        .all()
    )
    for line in lines:
        if not line.item_id:
            continue
        _apply_stock_in(
            db,
            int(line.item_id),
            int(req.warehouse_id),
            int(line.quantity),
            ref_type="purchase_request",
            ref_id=request_id,
            user_id=req.warehouse_posted_by or req.requester_id,
        )


def advance_workflow_after_step(
    db: Session,
    instance_id: int,
    *,
    completed_order: int,
    actor: User,
    payment_method: str | None = None,
    payment_comment: str | None = None,
    payment_location: str | None = None,
    check_plan: list | None = None,
) -> None:
    instance = db.get(WorkflowInstance, instance_id)
    if not instance:
        return

    _on_purchase_step_completed(
        db,
        instance,
        completed_order,
        payment_method=payment_method,
        payment_comment=payment_comment,
        payment_location=payment_location,
        check_plan=check_plan,
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

        if can_auto_skip_next_approval_step(db, instance, actor, next_step):
            _complete_step_record(
                db,
                next_step,
                actor,
                comment=AUTO_SKIP_COMMENT,
            )
            mark_inbox_done_for_workflow(db, instance_id, user_id=actor.id)
            db.flush()
            _on_purchase_step_completed(
                db,
                instance,
                next_step.order,
                payment_method=payment_method,
                payment_comment=payment_comment,
                payment_location=payment_location,
                check_plan=check_plan,
            )
            continue

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
    sepidar_confirmed: bool = False,
) -> None:
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

    _assert_operational_ready(db, request_id, expected_action, sepidar_confirmed=sepidar_confirmed)

    if expected_action == ACTION_MARK_PAYMENT:
        req = db.get(Request, request_id)
        if req:
            req.sepidar_registered_by = user.id
            req.invoice_paid_by = user.id
    elif expected_action == ACTION_CONFIRM_RECEIPT:
        req = db.get(Request, request_id)
        if req:
            req.goods_received_by = user.id
    elif expected_action == ACTION_CONFIRM_WAREHOUSE_SEPIDAR:
        req = db.get(Request, request_id)
        if req:
            req.sepidar_confirmed_by = user.id
            req.warehouse_posted_by = user.id

    _complete_step_record(db, step, user, comment=comment)
    mark_inbox_done_for_workflow(db, inst.id, user_id=user.id)
    db.flush()

    advance_workflow_after_step(
        db,
        inst.id,
        completed_order=step.order,
        actor=user,
    )
    db.refresh(inst)
    from app.services.workflow_notifications import notify_submitter_step_decision

    notify_submitter_step_decision(
        db,
        instance_id=inst.id,
        decision="approved",
        step_order=step.order,
        actor=user,
        comment=comment,
        final=inst.status == "approved",
    )
    db.commit()


def _assert_operational_ready(
    db: Session,
    request_id: int,
    action: str,
    *,
    sepidar_confirmed: bool = False,
) -> None:
    from app.services.attachment_service import (
        ENTITY_PROCUREMENT_BOL,
        ENTITY_PROCUREMENT_INVOICE,
        ENTITY_PROCUREMENT_PAYMENT_SLIP,
        list_attachments_serialized,
    )

    if action == ACTION_FILL_STOCK:
        lines = (
            db.query(RequestItem)
            .filter(RequestItem.request_id == request_id)
            .all()
        )
        if not lines:
            raise ValueError("اقلام خرید یافت نشد")
        missing = [li for li in lines if li.warehouse_stock is None]
        if missing:
            raise ValueError("برای همه اقلام، ستون موجودی انبار را وارد کنید")
    elif action == ACTION_UPLOAD_PROFORMA:
        if not _has_submitted_proforma(db, request_id):
            raise ValueError("ابتدا پیش‌فاکتور را ثبت و «ارسال برای تأیید» کنید")
    elif action == ACTION_UPLOAD_INVOICE:
        if not list_attachments_serialized(db, ENTITY_PROCUREMENT_INVOICE, request_id):
            raise ValueError("ابتدا فایل فاکتور را بارگذاری کنید")
    elif action == ACTION_MARK_PAYMENT:
        if not list_attachments_serialized(
            db, ENTITY_PROCUREMENT_PAYMENT_SLIP, request_id
        ):
            raise ValueError(
                "قبل از ثبت سپیدار، تصویر فیش واریزی یا چک‌های پرداخت‌شده را بارگذاری کنید"
            )
    elif action == ACTION_UPLOAD_BOL:
        if not list_attachments_serialized(db, ENTITY_PROCUREMENT_BOL, request_id):
            raise ValueError("ابتدا فایل بارنامه را بارگذاری کنید")
    elif action == ACTION_CONFIRM_WAREHOUSE_SEPIDAR:
        if not sepidar_confirmed:
            raise ValueError("تیک «در سپیدار ثبت شده است» الزامی است")
        req = db.get(Request, request_id)
        if not req or not req.warehouse_id:
            raise ValueError("انبار مقصد مشخص نیست")


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


def _proforma_amount(db: Session, request_id: int) -> Decimal | None:
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
    if not row or row.amount is None:
        return None
    return Decimal(str(row.amount))


def validate_ceo_payment_terms(
    db: Session,
    request_id: int,
    *,
    payment_location: str | None,
    payment_method: str | None,
    check_plan: list | None,
) -> tuple[str, str, list | None]:
    loc = (payment_location or "").strip().lower()
    method = (payment_method or "").strip().lower()
    if method in ("نقدی", "cash"):
        method = PAYMENT_METHOD_CASH
    elif method in ("چک", "check", "cheque"):
        method = PAYMENT_METHOD_CHECK
    if loc in ("بانک", "bank"):
        loc = PAYMENT_LOCATION_BANK
    elif loc in ("تنخواه", "petty_cash", "petty-cash"):
        loc = PAYMENT_LOCATION_PETTY_CASH

    if loc not in PAYMENT_LOCATIONS:
        raise ValueError("محل پرداخت باید «بانک» یا «تنخواه» باشد")
    if method not in PURCHASE_PAYMENT_METHODS:
        raise ValueError("روش پرداخت باید «نقدی» یا «چک» باشد")

    normalized_plan: list | None = None
    if method == PAYMENT_METHOD_CHECK:
        if not check_plan or not isinstance(check_plan, list):
            raise ValueError("برای پرداخت چکی، برنامه چک‌ها (تعداد، مبلغ، تاریخ) الزامی است")
        total = Decimal("0")
        normalized_plan = []
        for i, row in enumerate(check_plan, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"ردیف چک {i} نامعتبر است")
            amount = row.get("amount")
            due = row.get("dueDate") or row.get("due_date")
            if amount is None:
                raise ValueError(f"مبلغ چک ردیف {i} الزامی است")
            try:
                amt = Decimal(str(amount))
            except Exception as exc:
                raise ValueError(f"مبلغ چک ردیف {i} نامعتبر است") from exc
            if amt <= 0:
                raise ValueError(f"مبلغ چک ردیف {i} باید مثبت باشد")
            if not due:
                raise ValueError(f"تاریخ سررسید چک ردیف {i} الزامی است")
            if isinstance(due, date):
                due_s = due.isoformat()
            else:
                due_s = str(due).strip()
                try:
                    date.fromisoformat(due_s)
                except ValueError as exc:
                    raise ValueError(f"تاریخ سررسید چک ردیف {i} نامعتبر است") from exc
            total += amt
            normalized_plan.append({"amount": float(amt), "dueDate": due_s})
        expected = _proforma_amount(db, request_id)
        if expected is not None and total != expected:
            raise ValueError(
                f"جمع مبالغ چک‌ها ({total}) باید برابر مبلغ پیش‌فاکتور ({expected}) باشد"
            )
    return loc, method, normalized_plan


def repair_stuck_purchase_operational_steps(db: Session, request_id: int) -> bool:
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
        if action == ACTION_UPLOAD_BOL:
            from app.services.attachment_service import (
                ENTITY_PROCUREMENT_BOL,
                list_attachments_serialized,
            )

            if list_attachments_serialized(db, ENTITY_PROCUREMENT_BOL, request_id):
                complete_operational_step(
                    db,
                    request_id=request_id,
                    user_or_id=assignee,
                    expected_action=ACTION_UPLOAD_BOL,
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
    *,
    payment_executed: bool = False,
    sepidar_confirmed: bool = False,
) -> bool:
    if instance.ref_type != WORKFLOW_REF_PURCHASE:
        return False
    action = step_action_for_order(db, instance.ref_type, step.order)
    request_id = int(instance.ref_id)

    if action == ACTION_FILL_STOCK:
        try:
            complete_operational_step(
                db,
                request_id=request_id,
                user_or_id=user,
                expected_action=ACTION_FILL_STOCK,
            )
            return True
        except ValueError:
            return False

    if action == ACTION_MARK_PAYMENT:
        if not payment_executed:
            return False
        complete_operational_step(
            db,
            request_id=request_id,
            user_or_id=user,
            expected_action=ACTION_MARK_PAYMENT,
        )
        return True

    if action == ACTION_CONFIRM_RECEIPT:
        complete_operational_step(
            db,
            request_id=request_id,
            user_or_id=user,
            expected_action=ACTION_CONFIRM_RECEIPT,
        )
        return True

    if action == ACTION_CONFIRM_WAREHOUSE_SEPIDAR:
        if not sepidar_confirmed:
            return False
        complete_operational_step(
            db,
            request_id=request_id,
            user_or_id=user,
            expected_action=ACTION_CONFIRM_WAREHOUSE_SEPIDAR,
            sepidar_confirmed=True,
        )
        return True

    if action not in (ACTION_UPLOAD_PROFORMA, ACTION_UPLOAD_INVOICE, ACTION_UPLOAD_BOL):
        return False

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
    payment_location: str | None = None,
    check_plan: list | None = None,
    payment_executed: bool = False,
    sepidar_confirmed: bool = False,
) -> None:
    if instance.ref_type != WORKFLOW_REF_PURCHASE:
        return
    action = step_action_for_order(db, instance.ref_type, step.order)
    request_id = int(instance.ref_id)

    if action == ACTION_FILL_STOCK:
        _assert_operational_ready(db, request_id, ACTION_FILL_STOCK)
        return
    if action == ACTION_UPLOAD_PROFORMA:
        if _has_submitted_proforma(db, request_id):
            raise ValueError(
                "پیش‌فاکتور ارسال شده است؛ گردش‌کار در حال به‌روزرسانی است. "
                "صفحه را رفرش کنید."
            )
        raise ValueError(
            "ثبت و «ارسال برای تأیید» پیش‌فاکتور از صفحه درخواست خرید انجام می‌شود"
        )
    if action == ACTION_UPLOAD_INVOICE:
        raise ValueError("بارگذاری فاکتور از صفحه درخواست خرید انجام می‌شود")
    if action == ACTION_UPLOAD_BOL:
        raise ValueError("بارگذاری بارنامه از صفحه درخواست خرید انجام می‌شود")
    if action == ACTION_MARK_PAYMENT:
        if not payment_executed:
            raise ValueError(
                "ثبت در سپیدار و پرداخت از دکمه «ثبت در سپیدار انجام شد» انجام می‌شود"
            )
        _assert_operational_ready(db, request_id, ACTION_MARK_PAYMENT)
        return
    if action == ACTION_CONFIRM_WAREHOUSE_SEPIDAR:
        if not sepidar_confirmed:
            raise ValueError("تیک «در سپیدار ثبت شده است» الزامی است")
        _assert_operational_ready(
            db, request_id, ACTION_CONFIRM_WAREHOUSE_SEPIDAR, sepidar_confirmed=True
        )
        return
    if action == ACTION_APPROVE_PROFORMA:
        validate_ceo_payment_terms(
            db,
            request_id,
            payment_location=payment_location,
            payment_method=payment_method,
            check_plan=check_plan,
        )
