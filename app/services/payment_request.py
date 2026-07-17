from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.messaging.publisher import publish_event
from app.models.payment_request import PaymentRequest
from app.models.workflow_instance import WorkflowInstance
from app.constants.payment_methods import normalize_payment_method
from app.constants.payment_order import (
    PAYMENT_ORDER_KIND_COLLECTIVE,
    PAYMENT_ORDER_KIND_INDIVIDUAL,
    WORKFLOW_REF_PAYMENT_ORDER,
)
from app.constants.payment_types import (
    EMPLOYEE_FINANCIAL_TYPES,
    PAYMENT_TYPE_ADVANCE,
    PAYMENT_TYPE_LOAN,
    PAYMENT_TYPE_PAYMENT_ORDER,
)
from app.models.counterparty import Counterparty
from app.models.company_bank_account import CompanyBankAccount
from app.models.counterparty_bank_account import CounterpartyBankAccount
from app.schemas.forms import LoanAdvanceRequestUpdate, PaymentRequestUpdate
from app.services import company_bank_account as cba_svc
from app.services import counterparty_bank_account as cp_ba_svc
from app.services.bank_account_utils import bank_account_to_dict
from app.services.payment_request_terms import workflow_has_approved_step
from app.services.crud_utils import ensure_editable
from app.services.workflow_lock import ensure_workflow_mutable_for_entity
from app.services.attachment_service import (
    ENTITY_PAYMENT_REQUEST,
    count_attachments_batch,
    delete_all_for_entity,
    list_attachments,
    serialize_attachment,
)
from app.services.workflow_cleanup import cancel_workflow_for_ref
from app.models.user import User
from app.services.payment_request_access import (
    get_payment_request_by_workflow_instance,
    user_can_access_payment_request,
    user_can_edit_payment_request_as_requester,
    workflow_instance_for_payment,
)
from app.services.payment_request_list_scope import (
    apply_payment_request_list_scope,
    assert_scope_allowed,
    list_available_scopes,
)
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def _counterparty_brief(cp: Counterparty | None) -> dict | None:
    if not cp:
        return None
    return {
        "id": cp.id,
        "name": cp.name,
        "party_type": cp.party_type,
        "company_name": cp.company_name,
        "account_number": cp.account_number,
        "sheba_number": cp.sheba_number,
        "card_number": cp.card_number,
    }


def _bank_row_detail(row) -> dict:
    d = bank_account_to_dict(row)
    return {
        "id": row.id,
        "label": d["label"],
        "bank_name": d.get("bankName"),
        "account_number": d.get("accountNumber"),
        "sheba_number": d.get("shebaNumber"),
        "card_number": d.get("cardNumber"),
        "display_label": d.get("displayLabel"),
    }


def _account_detail(db: Session, pr: PaymentRequest) -> tuple[dict | None, dict | None]:
    payer_detail = None
    receiver_detail = None
    if pr.payer_company_account_id:
        row = db.get(CompanyBankAccount, pr.payer_company_account_id)
        if row:
            payer_detail = _bank_row_detail(row)
    if pr.receiver_counterparty_account_id:
        row = db.get(CounterpartyBankAccount, pr.receiver_counterparty_account_id)
        if row:
            receiver_detail = _bank_row_detail(row)
    return payer_detail, receiver_detail


def _parse_receiver_snapshot(snap: str | None) -> tuple[str | None, str | None]:
    """از اسنپ‌شات «نام | شماره» فیلدهای ساختاریافته بساز."""
    raw = (snap or "").strip()
    if not raw or raw == "پرداخت جمعی":
        return None, None
    if " | " in raw:
        name, account = raw.split(" | ", 1)
        name = name.strip() or None
        account = account.strip() or None
        if account and account.endswith("..."):
            account = account.rstrip(".").strip() or account
        return name, account
    return raw, raw


def _payment_to_dict(
    db: Session, pr: PaymentRequest, cp: Counterparty | None = None
) -> dict:
    payer_detail, receiver_detail = _account_detail(db, pr)
    snap_name, snap_account = _parse_receiver_snapshot(pr.receiver_account)
    # اگر حساب طرف‌حساب لینک نشده، از اسنپ‌شات دستور پرداخت جزئیات مقصد را بساز
    if receiver_detail is None and snap_account:
        sheba = snap_account if snap_account.upper().startswith("IR") else None
        receiver_detail = {
            "label": snap_name,
            "bank_name": None,
            "account_number": None if sheba else snap_account,
            "sheba_number": sheba,
            "card_number": None,
        }
    return {
        "id": pr.id,
        "requester_id": pr.requester_id,
        "counterparty_id": pr.counterparty_id,
        "counterparty": _counterparty_brief(cp),
        "payer_company_account_id": pr.payer_company_account_id,
        "receiver_counterparty_account_id": pr.receiver_counterparty_account_id,
        "payment_type": pr.payment_type,
        "payment_method": pr.payment_method,
        "amount": float(pr.amount),
        "payer_account": pr.payer_account,
        "receiver_account": pr.receiver_account,
        "receiver_name": snap_name,
        "receiver_account_number": snap_account,
        "payer_account_detail": payer_detail,
        "receiver_account_detail": receiver_detail,
        "payment_date": pr.payment_date,
        "reason": pr.reason,
        "installment_count": pr.installment_count,
        "first_installment_date": pr.first_installment_date,
        "settlement_date": pr.settlement_date,
        "payment_order_kind": pr.payment_order_kind,
        "payment_marked_at": pr.payment_marked_at,
        "payment_marked_by": pr.payment_marked_by,
        "sepidar_confirmed_at": pr.sepidar_confirmed_at,
        "sepidar_confirmed_by": pr.sepidar_confirmed_by,
        "status": pr.status,
        "created_at": pr.created_at,
    }


def serialize_payment_request(
    db: Session,
    pr: PaymentRequest,
    *,
    workflow_instance_id: int | None = None,
    include_attachments: bool = True,
    attachment_count_override: int | None = None,
) -> dict:
    cp = db.get(Counterparty, pr.counterparty_id) if pr.counterparty_id else None
    base = _payment_to_dict(db, pr, cp)
    requester = db.get(User, pr.requester_id)
    if requester:
        base["requester_name"] = requester.full_name
    if workflow_instance_id is None:
        inst = workflow_instance_for_payment(db, pr.id)
        workflow_instance_id = inst.id if inst else None
    base["workflow_instance_id"] = workflow_instance_id
    if include_attachments:
        atts = list_attachments(db, ENTITY_PAYMENT_REQUEST, pr.id)
        base["attachments"] = [serialize_attachment(a) for a in atts]
        base["attachment_count"] = len(atts)
    else:
        base["attachments"] = []
        base["attachment_count"] = (
            attachment_count_override if attachment_count_override is not None else 0
        )
    return base


def assert_payment_access(db: Session, user, pr: PaymentRequest | None) -> PaymentRequest:
    if not pr:
        raise ValueError("payment request not found")
    if not user_can_access_payment_request(db, user, pr):
        raise ValueError("access denied")
    return pr


def assert_payment_edit_as_requester(db: Session, user, pr: PaymentRequest) -> None:
    from app.services.workflow_lock import user_may_bypass_workflow_edit_lock

    if not user_can_edit_payment_request_as_requester(user, pr) and not user_may_bypass_workflow_edit_lock(
        user
    ):
        raise ValueError("access denied")
    ensure_editable(pr)
    ensure_workflow_mutable_for_entity(
        db,
        ref_type="payment_request",
        ref_id=pr.id,
        user=user,
    )


def _create_employee_financial_request(
    db: Session,
    *,
    requester_id: int,
    payment_type: str,
    amount: float,
    payment_date: date | None,
    reason: str | None,
    assignees_by_order: dict[str, int] | None = None,
):
    return create_payment_request(
        db=db,
        requester_id=requester_id,
        payment_type=payment_type,
        amount=amount,
        payer_account="-",
        receiver_account="-",
        payment_date=payment_date,
        reason=reason,
        assignees_by_order=assignees_by_order,
    )


def create_loan_request(
    db: Session,
    requester_id: int,
    amount: float,
    payment_date: date | None,
    reason: str | None,
    assignees_by_order: dict[str, int] | None = None,
):
    return _create_employee_financial_request(
        db,
        requester_id=requester_id,
        payment_type=PAYMENT_TYPE_LOAN,
        amount=amount,
        payment_date=payment_date,
        reason=reason,
        assignees_by_order=assignees_by_order,
    )


def create_advance_request(
    db: Session,
    requester_id: int,
    amount: float,
    payment_date: date | None,
    reason: str | None,
    assignees_by_order: dict[str, int] | None = None,
):
    return _create_employee_financial_request(
        db,
        requester_id=requester_id,
        payment_type=PAYMENT_TYPE_ADVANCE,
        amount=amount,
        payment_date=payment_date,
        reason=reason,
        assignees_by_order=assignees_by_order,
    )


def _require_payment_method(value: str | None) -> str:
    method = normalize_payment_method(value)
    if not method:
        raise ValueError("روش پرداخت باید «چک» یا «حواله» باشد")
    return method


def create_payment_order(
    db: Session,
    requester_id: int,
    *,
    payment_order_kind: str,
    amount: float,
    payment_method: str,
    payment_date: date | None,
    reason: str | None,
    payer_company_account_id: int | None = None,
    counterparty_id: int | None = None,
    counterparty_bank_account_id: int | None = None,
    receiver_name: str | None = None,
    receiver_account_number: str | None = None,
    assignees_by_order: dict[str, int] | None = None,
):
    kind = (payment_order_kind or PAYMENT_ORDER_KIND_INDIVIDUAL).strip().lower()
    if kind not in (PAYMENT_ORDER_KIND_INDIVIDUAL, PAYMENT_ORDER_KIND_COLLECTIVE):
        raise ValueError("نوع دستور پرداخت باید individual یا collective باشد")

    method = _require_payment_method(payment_method)
    if payer_company_account_id:
        payer_snap, payer_id = cba_svc.resolve_payer_snapshot(db, payer_company_account_id)
    else:
        payer_snap = "تعیین نشده | 0000000000000"
        payer_id = None

    receiver_id: int | None = None
    cp_id: int | None = None
    receiver_snap = "پرداخت جمعی"

    if kind == PAYMENT_ORDER_KIND_INDIVIDUAL:
        manual_name = (receiver_name or "").strip()
        manual_account = (receiver_account_number or "").strip()
        if len(manual_name) < 2:
            raise ValueError("نام یا شماره اشتراک آب الزامی است")
        if len(manual_account) < 5:
            raise ValueError("شماره حساب مقصد الزامی است")

        receiver_snap = f"{manual_name} | {manual_account}"
        if len(receiver_snap) > 100:
            receiver_snap = receiver_snap[:97] + "..."

        if counterparty_id:
            cp = db.get(Counterparty, counterparty_id)
            if cp and cp.is_active:
                cp_id = counterparty_id
                if counterparty_bank_account_id:
                    _, receiver_id = cp_ba_svc.resolve_receiver_snapshot(
                        db, counterparty_id, counterparty_bank_account_id
                    )

    return create_payment_request(
        db=db,
        requester_id=requester_id,
        payment_type=PAYMENT_TYPE_PAYMENT_ORDER,
        amount=amount,
        payment_method=method,
        payer_account=payer_snap,
        receiver_account=receiver_snap,
        payment_date=payment_date,
        reason=reason,
        assignees_by_order=assignees_by_order,
        counterparty_id=cp_id,
        payer_company_account_id=payer_id,
        receiver_counterparty_account_id=receiver_id,
        payment_order_kind=kind,
        workflow_ref_type=WORKFLOW_REF_PAYMENT_ORDER,
    )


def create_payment_request(
    db: Session,
    requester_id: int,
    payment_type: str,
    amount: float,
    payer_account: str,
    receiver_account: str,
    payment_date: date | None,
    reason: str | None,
    assignees_by_order: dict[str, int] | None = None,
    counterparty_id: int | None = None,
    payer_company_account_id: int | None = None,
    receiver_counterparty_account_id: int | None = None,
    payment_method: str | None = None,
    payment_order_kind: str | None = None,
    workflow_ref_type: str | None = None,
):
    resolved_method: str | None = None
    if payment_type == PAYMENT_TYPE_PAYMENT_ORDER:
        kind = (payment_order_kind or PAYMENT_ORDER_KIND_INDIVIDUAL).strip().lower()
        if kind == PAYMENT_ORDER_KIND_INDIVIDUAL:
            if not counterparty_id:
                pass  # ورود دستی — بدون لینک به طرف‌حساب
            else:
                cp = db.get(Counterparty, counterparty_id)
                if not cp or not cp.is_active:
                    raise ValueError("طرف حساب یافت نشد یا غیرفعال است")
            # receiver از فیلدهای دستی یا snapshot پر می‌شود
        if not payment_method:
            raise ValueError("روش پرداخت (چک یا حواله) الزامی است")
        resolved_method = _require_payment_method(payment_method)
    resolved_payment_date = payment_date
    if isinstance(payment_date, str) and payment_date:
        resolved_payment_date = date.fromisoformat(payment_date)

    req = PaymentRequest(
        requester_id=requester_id,
        counterparty_id=counterparty_id,
        payer_company_account_id=payer_company_account_id,
        receiver_counterparty_account_id=receiver_counterparty_account_id,
        payment_type=payment_type,
        payment_method=resolved_method,
        amount=amount,
        payer_account=payer_account,
        receiver_account=receiver_account,
        payment_date=resolved_payment_date,
        reason=reason,
        payment_order_kind=payment_order_kind
        if payment_type == PAYMENT_TYPE_PAYMENT_ORDER
        else None,
        status="PENDING",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    wf_ref = workflow_ref_type or "payment_request"
    if payment_type == PAYMENT_TYPE_PAYMENT_ORDER and not workflow_ref_type:
        wf_ref = WORKFLOW_REF_PAYMENT_ORDER

    wf_payload: dict = {
        "ref_type": wf_ref,
        "ref_id": req.id,
        "submitter_id": requester_id,
    }
    if assignees_by_order:
        wf_payload["assignees_by_order"] = assignees_by_order

    from app.services.workflow_start import start_workflow_instance

    try:
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        db.rollback()
        raise
    publish_event("workflow.start", wf_payload)

    inst = workflow_instance_for_payment(db, req.id)
    return serialize_payment_request(
        db,
        req,
        workflow_instance_id=inst.id if inst else None,
        include_attachments=True,
    )


def list_payment_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    resolved_scope = assert_scope_allowed(db, viewer, scope)
    query = db.query(PaymentRequest)
    query = apply_payment_request_list_scope(db, query, user=viewer, scope=resolved_scope)
    query = apply_equal_filter(query, PaymentRequest, filter_by, filter_value)
    query = apply_search_filter(
        query,
        PaymentRequest,
        search,
        ["payment_type", "payer_account", "receiver_account", "reason", "status"],
    )
    query = apply_sort(query, PaymentRequest, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    ids = [r.id for r in rows]
    counts = count_attachments_batch(db, ENTITY_PAYMENT_REQUEST, ids)
    return [
        serialize_payment_request(
            db,
            pr,
            include_attachments=False,
            attachment_count_override=counts.get(pr.id, 0),
        )
        for pr in rows
    ]


def count_payment_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    resolved_scope = assert_scope_allowed(db, viewer, scope)
    query = db.query(func.count(PaymentRequest.id))
    query = apply_payment_request_list_scope(db, query, user=viewer, scope=resolved_scope)
    query = apply_equal_filter(query, PaymentRequest, filter_by, filter_value)
    query = apply_search_filter(
        query,
        PaymentRequest,
        search,
        ["payment_type", "payer_account", "receiver_account", "reason", "status"],
    )
    return query.scalar() or 0


def get_payment_request_list_capabilities(db: Session, viewer: User) -> dict:
    return {"scopes": list_available_scopes(db, viewer)}


def get_payment_request(db: Session, request_id: int) -> PaymentRequest | None:
    return db.get(PaymentRequest, request_id)


def get_payment_request_detail(db: Session, user, request_id: int) -> dict:
    pr = get_payment_request(db, request_id)
    assert_payment_access(db, user, pr)
    return serialize_payment_request(db, pr)


def get_payment_request_by_instance_detail(db: Session, user, instance_id: int) -> dict:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        raise ValueError("workflow instance not found")
    if inst.ref_type not in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
        raise ValueError("این نمونه workflow مربوط به درخواست پرداخت نیست")
    pr = get_payment_request_by_workflow_instance(db, instance_id)
    if not pr:
        raise ValueError(
            f"درخواست مالی با شناسه {inst.ref_id} یافت نشد؛ "
            "احتمالاً رکورد حذف شده یا داده ناسازگار است. این کار را از کارتابل رد کنید."
        )
    assert_payment_access(db, user, pr)
    return serialize_payment_request(db, pr, workflow_instance_id=instance_id)


def update_payment_request(
    db: Session,
    request_id: int,
    payload: PaymentRequestUpdate,
    *,
    user,
) -> dict:
    req = db.get(PaymentRequest, request_id)
    if not req:
        raise ValueError("payment request not found")
    assert_payment_edit_as_requester(db, user, req)

    if req.payment_type in EMPLOYEE_FINANCIAL_TYPES:
        if isinstance(payload, LoanAdvanceRequestUpdate):
            la = payload
        else:
            la = LoanAdvanceRequestUpdate(
                amount=payload.amount,
                payment_date=payload.payment_date,
                reason=payload.reason,
            )
        if la.amount is not None:
            req.amount = la.amount
        if la.payment_date is not None:
            req.payment_date = la.payment_date
        if la.reason is not None:
            req.reason = la.reason
    else:
        if payload.payment_type is not None:
            req.payment_type = payload.payment_type
        if payload.amount is not None:
            req.amount = payload.amount
        if payload.payer_account is not None:
            req.payer_account = payload.payer_account
        if payload.receiver_account is not None:
            req.receiver_account = payload.receiver_account
        if payload.payment_date is not None:
            req.payment_date = payload.payment_date
        if payload.reason is not None:
            req.reason = payload.reason
        if payload.payment_method is not None and req.payment_type == PAYMENT_TYPE_PAYMENT_ORDER:
            req.payment_method = _require_payment_method(payload.payment_method)

    db.commit()
    db.refresh(req)
    return serialize_payment_request(db, req)


def update_loan_advance_request(
    db: Session,
    request_id: int,
    payload: LoanAdvanceRequestUpdate,
    *,
    user,
) -> dict:
    req = db.get(PaymentRequest, request_id)
    if not req:
        raise ValueError("payment request not found")
    if req.payment_type not in EMPLOYEE_FINANCIAL_TYPES:
        raise ValueError("این درخواست وام یا مساعده نیست")
    return update_payment_request(db, request_id, payload, user=user)


def delete_payment_request(db: Session, request_id: int, *, user) -> None:
    req = db.get(PaymentRequest, request_id)
    if not req:
        raise ValueError("payment request not found")
    assert_payment_edit_as_requester(db, user, req)
    cancel_workflow_for_ref(db, "payment_request", request_id)
    delete_all_for_entity(db, ENTITY_PAYMENT_REQUEST, request_id)
    db.delete(req)
    db.commit()
