from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.constants.payment_types import EMPLOYEE_FINANCIAL_TYPES
from app.core.database import get_db
from app.constants.api_permissions import PAYMENT_ACCESS
from app.dependencies.auth import require_any_permission, require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.forms import (
    LoanAdvanceRequestCreate,
    LoanAdvanceRequestUpdate,
    PaymentOrderCreate,
    PaymentRequestCreate,
    PaymentRequestUpdate,
)
from app.schemas.attachment import AttachmentOut
from app.schemas.payment_request import (
    PaymentRequestListResponse,
    PaymentRequestOut,
)
from app.services.attachment_service import (
    ENTITY_PAYMENT_REQUEST,
    delete_entity_attachment,
    list_attachments_serialized,
    save_entity_attachment,
    serialize_attachment,
)
from app.services import company_bank_account as cba_svc
from app.services import counterparty_bank_account as cp_ba_svc
from app.services.payment_request import (
    assert_payment_edit_as_requester,
    count_payment_requests,
    create_advance_request,
    create_loan_request,
    create_payment_order,
    create_payment_request,
    delete_payment_request,
    get_payment_request,
    get_payment_request_by_instance_detail,
    get_payment_request_detail,
    get_payment_request_list_capabilities,
    list_payment_requests,
    update_loan_advance_request,
    update_payment_request,
)

router = APIRouter(prefix="/payment-requests", tags=["Payment Requests"])


@router.post("/loan", response_model=PaymentRequestOut, status_code=status.HTTP_201_CREATED)
def create_loan_request_api(
    payload: LoanAdvanceRequestCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        return create_loan_request(
            db=db,
            requester_id=user.id,
            amount=payload.amount,
            payment_date=payload.payment_date,
            reason=payload.reason,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post(
    "/advance",
    response_model=PaymentRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_advance_request_api(
    payload: LoanAdvanceRequestCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        return create_advance_request(
            db=db,
            requester_id=user.id,
            amount=payload.amount,
            payment_date=payload.payment_date,
            reason=payload.reason,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post(
    "/payment-order",
    response_model=PaymentRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_order_api(
    payload: PaymentOrderCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        return create_payment_order(
            db=db,
            requester_id=user.id,
            payment_order_kind=payload.payment_order_kind,
            counterparty_id=payload.counterparty_id,
            amount=payload.amount,
            payment_method=payload.payment_method,
            payer_company_account_id=payload.payer_company_account_id,
            counterparty_bank_account_id=payload.counterparty_bank_account_id,
            payment_date=payload.payment_date,
            reason=payload.reason,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/", response_model=PaymentRequestOut, status_code=status.HTTP_201_CREATED)
def create_payment_request_api(
    payload: PaymentRequestCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        payer_account = payload.payer_account or "-"
        receiver_account = payload.receiver_account or "-"
        payer_company_account_id = payload.payer_company_account_id
        receiver_counterparty_account_id = payload.counterparty_bank_account_id
        if payload.payment_type == "payment_order":
            if not payload.counterparty_id:
                raise ValueError("برای دستور پرداخت انتخاب طرف حساب الزامی است")
            if not payer_company_account_id or not receiver_counterparty_account_id:
                raise ValueError("انتخاب حساب مبدأ و مقصد الزامی است")
            payer_account, payer_company_account_id = cba_svc.resolve_payer_snapshot(
                db, payer_company_account_id
            )
            receiver_account, receiver_counterparty_account_id = (
                cp_ba_svc.resolve_receiver_snapshot(
                    db,
                    payload.counterparty_id,
                    receiver_counterparty_account_id,
                )
            )
        return create_payment_request(
            db=db,
            requester_id=user.id,
            payment_type=payload.payment_type,
            amount=payload.amount,
            payer_account=payer_account,
            receiver_account=receiver_account,
            payment_date=payload.payment_date,
            reason=payload.reason,
            assignees_by_order=payload.assignees_by_order,
            counterparty_id=payload.counterparty_id,
            payer_company_account_id=payer_company_account_id,
            receiver_counterparty_account_id=receiver_counterparty_account_id,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/list-capabilities")
def payment_request_list_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    return get_payment_request_list_capabilities(db, user)


@router.get("/", response_model=PaymentRequestListResponse)
def list_payment_requests_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    scope: str | None = Query(
        None,
        description="mine | team | all | approver | participated",
    ),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        offset = (page - 1) * page_size
        items = list_payment_requests(
            db,
            viewer=user,
            scope=scope,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_by=filter_by,
            filter_value=filter_value,
            search=search,
        )
        total = count_payment_requests(
            db,
            viewer=user,
            scope=scope,
            filter_by=filter_by,
            filter_value=filter_value,
            search=search,
        )
    except ValueError as err:
        raise_from_value_error(err)
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get(
    "/{request_id}/attachments",
    response_model=list[AttachmentOut],
)
def list_payment_attachments_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        get_payment_request_detail(db, user, request_id)
    except ValueError as err:
        raise_from_value_error(err)
    return list_attachments_serialized(db, ENTITY_PAYMENT_REQUEST, request_id)


@router.get("/by-workflow-instance/{instance_id}", response_model=PaymentRequestOut)
def get_payment_request_by_workflow_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return get_payment_request_by_instance_detail(db, user, instance_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{request_id}", response_model=PaymentRequestOut)
def get_payment_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return get_payment_request_detail(db, user, request_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.put("/{request_id}", response_model=PaymentRequestOut)
@router.patch("/{request_id}", response_model=PaymentRequestOut)
def update_payment_request_api(
    request_id: int,
    payload: PaymentRequestUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        pr = get_payment_request(db, request_id)
        if pr and pr.payment_type in EMPLOYEE_FINANCIAL_TYPES:
            la_payload = LoanAdvanceRequestUpdate(
                amount=payload.amount,
                payment_date=payload.payment_date,
                reason=payload.reason,
            )
            return update_loan_advance_request(
                db, request_id, la_payload, user=user
            )
        return update_payment_request(db, request_id, payload, user=user)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission("payment.create")),
):
    try:
        delete_payment_request(db, request_id, user=user)
    except ValueError as err:
        raise_from_value_error(err)


@router.post(
    "/{request_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_payment_attachment(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission("payment.create")),
):
    pr = get_payment_request(db, request_id)
    if not pr:
        raise HTTPException(status_code=404, detail="payment request not found")
    try:
        assert_payment_edit_as_requester(db, user, pr)
    except ValueError as err:
        raise_from_value_error(err)

    att = await save_entity_attachment(
        db,
        entity_type=ENTITY_PAYMENT_REQUEST,
        entity_id=request_id,
        uploaded_by_id=user.id,
        file=file,
    )
    return serialize_attachment(att)


@router.delete(
    "/{request_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_payment_attachment_api(
    request_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission("payment.create")),
):
    pr = get_payment_request(db, request_id)
    if not pr:
        raise HTTPException(status_code=404, detail="payment request not found")
    try:
        assert_payment_edit_as_requester(db, user, pr)
    except ValueError as err:
        raise_from_value_error(err)

    if not delete_entity_attachment(
        db,
        entity_type=ENTITY_PAYMENT_REQUEST,
        entity_id=request_id,
        attachment_id=attachment_id,
    ):
        raise HTTPException(status_code=404, detail="پیوست یافت نشد")
