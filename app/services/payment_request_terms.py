"""شرایط وام و مساعده — فقط تأییدکننده workflow، نه درخواست‌دهنده."""

from datetime import date

from sqlalchemy.orm import Session

from app.constants.payment_methods import normalize_payment_method
from app.constants.payment_types import (
    EMPLOYEE_FINANCIAL_TYPES,
    PAYMENT_TYPE_ADVANCE,
    PAYMENT_TYPE_LOAN,
    PAYMENT_TYPE_PAYMENT_ORDER,
)
from app.models.payment_request import PaymentRequest
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services import company_bank_account as cba_svc
from app.constants.payment_order import WORKFLOW_REF_PAYMENT_ORDER
from app.services.payment_request_access import workflow_instance_for_payment
from app.services.workflow_step_access import user_can_act_on_workflow_step as _user_can_act_on_step
from app.services.workflow_step_kinds import step_is_financial


PAYER_PENDING_MARKERS = frozenset(
    {
        "-",
        "0000000000000",
        "تعیین نشده",
        "تعیین نشده | 0000000000000",
    }
)


class ApproverTermsPayload:
    def __init__(
        self,
        *,
        amount: float | None = None,
        payment_date: date | None = None,
        installment_count: int | None = None,
        first_installment_date: date | None = None,
        settlement_date: date | None = None,
        payer_company_account_id: int | None = None,
        payer_account: str | None = None,
        payment_method: str | None = None,
    ):
        self.amount = amount
        self.payment_date = payment_date
        self.installment_count = installment_count
        self.first_installment_date = first_installment_date
        self.settlement_date = settlement_date
        self.payer_company_account_id = payer_company_account_id
        self.payer_account = payer_account
        self.payment_method = payment_method


def payer_is_unset(payer_account: str | None) -> bool:
    raw = (payer_account or "").strip()
    if not raw or raw in PAYER_PENDING_MARKERS:
        return True
    if "|" in raw:
        name, _, num = raw.partition("|")
        name = name.strip()
        num = num.strip()
        if not name or not num:
            return True
        if name in PAYER_PENDING_MARKERS or num in PAYER_PENDING_MARKERS:
            return True
    return False


def payment_terms_complete(pr: PaymentRequest) -> bool:
    if pr.payment_type == PAYMENT_TYPE_LOAN:
        return (
            pr.installment_count is not None
            and pr.installment_count >= 1
            and pr.first_installment_date is not None
        )
    if pr.payment_type == PAYMENT_TYPE_ADVANCE:
        return pr.settlement_date is not None
    if pr.payment_type == PAYMENT_TYPE_PAYMENT_ORDER:
        return normalize_payment_method(pr.payment_method) is not None
    return True


def financial_terms_satisfied(pr: PaymentRequest) -> bool:
    if pr.payment_type == PAYMENT_TYPE_PAYMENT_ORDER:
        return payment_terms_complete(pr) and (
            not payer_is_unset(pr.payer_account) or pr.payer_company_account_id is not None
        )
    return payment_terms_complete(pr) and (
        not payer_is_unset(pr.payer_account) or pr.payer_company_account_id is not None
    )


def workflow_has_approved_step(db: Session, payment_request_id: int) -> bool:
    inst = workflow_instance_for_payment(db, payment_request_id)
    if not inst:
        return False
    return (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.instance_id == inst.id,
            WorkflowStep.status == "approved",
        )
        .count()
        > 0
    )


def _pending_step(db: Session, instance_id: int) -> WorkflowStep | None:
    return (
        db.query(WorkflowStep)
        .filter_by(instance_id=instance_id, status="pending")
        .order_by(WorkflowStep.order)
        .first()
    )


def must_collect_financial_terms(
    db: Session,
    inst: WorkflowInstance,
    pr: PaymentRequest,
    step: WorkflowStep,
) -> bool:
    """فقط مرحلهٔ جاریِ مالی — نه مرحلهٔ مدیر مستقیم."""
    if financial_terms_satisfied(pr):
        return False
    return step_is_financial(db, inst, step)


def _apply_payment_order_terms(
    db: Session,
    inst: WorkflowInstance,
    pr: PaymentRequest,
    step: WorkflowStep,
    user,
    terms: ApproverTermsPayload | None,
) -> None:
    if not _user_can_act_on_step(user, step):
        raise ValueError("access denied")

    if terms and terms.payment_method:
        pr.payment_method = normalize_payment_method(terms.payment_method)
        if not pr.payment_method:
            raise ValueError("روش پرداخت باید «چک» یا «حواله» باشد")

    if payer_is_unset(pr.payer_account) and not pr.payer_company_account_id:
        if terms is None or not terms.payer_company_account_id:
            if step_is_financial(db, inst, step):
                raise ValueError(
                    "برای تأیید دستور پرداخت، حساب بانکی مبدأ (شرکت) را انتخاب کنید"
                )
        elif terms.payer_company_account_id:
            snap, acc_id = cba_svc.resolve_payer_snapshot(
                db, terms.payer_company_account_id
            )
            pr.payer_account = snap
            pr.payer_company_account_id = acc_id

    if not pr.payment_method:
        raise ValueError("روش پرداخت (چک یا حواله) را انتخاب کنید")

    db.flush()


def terms_touch_financial_numbers(terms: ApproverTermsPayload | None) -> bool:
    if terms is None:
        return False
    return any(
        (
            terms.amount is not None,
            terms.payment_date is not None,
            terms.installment_count is not None,
            terms.first_installment_date is not None,
            terms.settlement_date is not None,
            terms.payer_company_account_id is not None,
            bool((terms.payer_account or "").strip()),
            terms.payment_method is not None,
        )
    )


def _assert_can_mutate_financial_numbers(entity, *, step_action: str | None = None) -> None:
    from app.constants.financial_workflow import (
        ACTION_MARK_PAYMENT,
        CONFIRM_SEPIDAR_ACTIONS,
    )
    from app.services.financial_workflow import assert_financial_numbers_unlocked

    if step_action == ACTION_MARK_PAYMENT or step_action in CONFIRM_SEPIDAR_ACTIONS:
        raise ValueError(
            "در مرحله ثبت یا تأیید سپیدار، تغییر مبلغ و شرایط مالی مجاز نیست"
        )
    assert_financial_numbers_unlocked(entity)


def _apply_amount_and_payment_date(
    db: Session,
    inst: WorkflowInstance,
    step: WorkflowStep,
    user,
    terms: ApproverTermsPayload | None,
    *,
    step_action: str | None = None,
) -> None:
    if terms is None or (terms.amount is None and terms.payment_date is None):
        return
    if not _user_can_act_on_step(user, step):
        raise ValueError("access denied")

    if inst.ref_type in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
        pr = db.get(PaymentRequest, inst.ref_id)
        if not pr:
            return
        _assert_can_mutate_financial_numbers(pr, step_action=step_action)
        if terms.amount is not None and terms.amount > 0:
            pr.amount = terms.amount
        if terms.payment_date is not None:
            pr.payment_date = terms.payment_date
        db.flush()
        return

    if inst.ref_type == "petty_cash":
        from app.models.petty_cash_request import PettyCashRequest

        row = db.get(PettyCashRequest, inst.ref_id)
        if not row:
            return
        _assert_can_mutate_financial_numbers(row, step_action=step_action)
        if terms.amount is not None and terms.amount > 0:
            row.amount = terms.amount
        if terms.payment_date is not None:
            row.requested_date = terms.payment_date
        db.flush()
        return

    if inst.ref_type == "financial_document":
        from app.models.financial_document import FinancialDocument

        row = db.get(FinancialDocument, inst.ref_id)
        if not row:
            return
        _assert_can_mutate_financial_numbers(row, step_action=step_action)
        if terms.amount is not None and terms.amount > 0:
            row.amount = terms.amount
        if terms.payment_date is not None:
            row.document_date = terms.payment_date
        db.flush()


def apply_approver_terms_before_approve(
    db: Session,
    instance_id: int,
    user,
    terms: ApproverTermsPayload | None,
) -> list[dict]:
    """
    شرایط مالی را اعمال می‌کند و لیست تغییرات فیلدها را برمی‌گرداند
    (برای تاریخچهٔ تأیید / audit).
    پس از ثبت در سپیدار، تغییر اعداد/شرایط مالی ممنوع است.
    """
    from app.services.financial_workflow import (
        is_financial_ref_type,
        load_financial_entity,
        step_action_for_order,
    )
    from app.services.workflow_terms_history import (
        diff_financial_terms,
        snapshot_financial_terms,
    )

    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return []

    step = _pending_step(db, instance_id)
    if not step:
        return []

    step_action = (
        step_action_for_order(db, inst.ref_type, step.order)
        if is_financial_ref_type(inst.ref_type)
        else None
    )

    if terms_touch_financial_numbers(terms):
        entity = (
            load_financial_entity(db, inst.ref_type, int(inst.ref_id))
            if is_financial_ref_type(inst.ref_type)
            else None
        )
        if entity is not None:
            _assert_can_mutate_financial_numbers(entity, step_action=step_action)

    before = snapshot_financial_terms(db, inst)

    _apply_amount_and_payment_date(
        db, inst, step, user, terms, step_action=step_action
    )

    if inst.ref_type in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
        pr = db.get(PaymentRequest, inst.ref_id)
        if pr:
            if pr.payment_type == PAYMENT_TYPE_PAYMENT_ORDER:
                if terms_touch_financial_numbers(terms):
                    _assert_can_mutate_financial_numbers(pr, step_action=step_action)
                _apply_payment_order_terms(db, inst, pr, step, user, terms)
            elif pr.payment_type in EMPLOYEE_FINANCIAL_TYPES:
                if must_collect_financial_terms(db, inst, pr, step):
                    _assert_can_mutate_financial_numbers(pr, step_action=step_action)
                    if payer_is_unset(pr.payer_account) and not pr.payer_company_account_id:
                        if terms is None or (
                            not terms.payer_company_account_id
                            and not (terms.payer_account or "").strip()
                        ):
                            raise ValueError(
                                "برای تأیید مالی، حساب بانکی مبدأ پرداخت (شرکت) را انتخاب کنید"
                            )
                        if terms.payer_company_account_id:
                            snap, acc_id = cba_svc.resolve_payer_snapshot(
                                db, terms.payer_company_account_id
                            )
                            pr.payer_account = snap
                            pr.payer_company_account_id = acc_id
                        else:
                            pr.payer_account = (terms.payer_account or "").strip()
                        db.flush()

                    if not payment_terms_complete(pr):
                        if pr.requester_id == user.id:
                            raise ValueError(
                                "درخواست‌دهنده نمی‌تواند تعداد اقساط، تاریخ شروع قسط یا تاریخ تسویه را تعیین کند"
                            )

                        if not _user_can_act_on_step(user, step):
                            raise ValueError("access denied")

                        if terms is None:
                            if pr.payment_type == PAYMENT_TYPE_LOAN:
                                raise ValueError(
                                    "برای تأیید وام، تعداد اقساط و تاریخ شروع قسط اول الزامی است"
                                )
                            raise ValueError("برای تأیید مساعده، تاریخ تسویه الزامی است")

                        if pr.payment_type == PAYMENT_TYPE_LOAN:
                            if (
                                terms.installment_count is None
                                or terms.installment_count < 1
                            ):
                                raise ValueError("تعداد اقساط باید حداقل ۱ باشد")
                            if terms.first_installment_date is None:
                                raise ValueError("تاریخ شروع قسط اول الزامی است")
                            pr.installment_count = terms.installment_count
                            pr.first_installment_date = terms.first_installment_date
                        elif pr.payment_type == PAYMENT_TYPE_ADVANCE:
                            if terms.settlement_date is None:
                                raise ValueError("تاریخ تسویه مساعده الزامی است")
                            pr.settlement_date = terms.settlement_date

                        db.flush()

    after = snapshot_financial_terms(db, inst)
    return diff_financial_terms(before, after)
