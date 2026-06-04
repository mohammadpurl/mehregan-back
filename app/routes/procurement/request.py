from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import (
    PAYMENT_WRITE,
    PROCUREMENT_READ,
    PROCUREMENT_WRITE,
    WORKFLOW_VIEW,
)
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.procurement import (
    CreateProcurementPaymentInput,
    CreatePurchaseRequestInput,
    PurchaseRequestOut,
    ProformaOut,
    UpdatePurchaseRequestInput,
)
from app.schemas.request import CreateRequestInput, UpdateRequestInput
from app.services.procurement.purchase_request_service import (
    count_purchase_requests,
    create_purchase_request,
    get_purchase_request_by_instance_detail,
    get_purchase_request_detail,
    get_purchase_request_detail_for_viewer,
    list_purchase_requests,
    update_purchase_request_lines,
)
from app.services.purchase_request_list_scope import get_purchase_request_list_capabilities
from app.services.procurement.proforma_service import (
    create_proforma,
    list_proformas_for_request,
    submit_proforma_for_approval,
)
from app.services.procurement.procurement_payment_service import create_procurement_payment
from app.services.procurement.purchase_order_service import ensure_purchase_order_for_request
from app.services.procurement.request_service import (
    count_requests,
    create_request,
    delete_request,
    get_request,
    list_requests,
    update_request,
)

router = APIRouter(prefix="/requests", tags=["Requests"])


@router.get("/purchase/list-capabilities")
def purchase_request_list_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    return get_purchase_request_list_capabilities(db, user)


@router.get("/purchase/warehouse-catalog")
def purchase_warehouse_catalog_api(
    warehouse_id: int | None = Query(None, alias="warehouseId"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_READ, *PROCUREMENT_WRITE)),
):
    from app.services.procurement.purchase_catalog_service import (
        list_purchase_warehouse_catalog,
    )

    return list_purchase_warehouse_catalog(
        db, warehouse_id=warehouse_id, search=search
    )


@router.get("/purchase")
def list_purchase_requests_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    scope: str | None = Query(
        None,
        description="mine | all | approver | participated",
    ),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    try:
        offset = (page - 1) * page_size
        items = list_purchase_requests(
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
        total = count_purchase_requests(
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


@router.post("/purchase", response_model=PurchaseRequestOut, status_code=status.HTTP_201_CREATED)
def create_purchase_request_api(
    payload: CreatePurchaseRequestInput,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return create_purchase_request(db, user_id=user.id, payload=payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/purchase/by-workflow-instance/{instance_id}", response_model=PurchaseRequestOut)
def get_purchase_request_by_workflow_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW, *PROCUREMENT_READ)),
):
    try:
        return get_purchase_request_by_instance_detail(db, user, instance_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/purchase/{request_id}", response_model=PurchaseRequestOut)
def get_purchase_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW, *PROCUREMENT_READ)),
):
    try:
        data = get_purchase_request_detail_for_viewer(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)
    if not data:
        raise HTTPException(status_code=404, detail="purchase request not found")
    return data


@router.patch("/purchase/{request_id}", response_model=PurchaseRequestOut)
def update_purchase_request_api(
    request_id: int,
    payload: UpdatePurchaseRequestInput,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return update_purchase_request_lines(
            db,
            request_id,
            user_id=user.id,
            lines=payload.lines,
            reason=payload.reason,
            actor=user,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/purchase/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        delete_request(db, request_id, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/purchase/{request_id}/proformas", response_model=list[ProformaOut])
def list_request_proformas_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW, *PROCUREMENT_READ)),
):
    from app.services.purchase_request_list_scope import user_can_access_purchase_request
    from app.services.permission import user_has_permission_db

    if not user_has_permission_db(db, user.id, "procurement.read"):
        if not user_can_access_purchase_request(db, user, request_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="access denied",
            )
    return list_proformas_for_request(db, request_id)


@router.post("/purchase/{request_id}/proformas", response_model=ProformaOut)
async def upload_proforma_api(
    request_id: int,
    supplier_id: int = Form(...),
    amount: float = Form(...),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return await create_proforma(
            db,
            request_id=request_id,
            user_id=user.id,
            supplier_id=supplier_id,
            amount=amount,
            file=file,
            notes=notes,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post(
    "/purchase/{request_id}/proformas/{proforma_id}/submit",
    response_model=ProformaOut,
)
def submit_proforma_api(
    request_id: int,
    proforma_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return submit_proforma_for_approval(
            db, request_id=request_id, proforma_id=proforma_id, user_id=user.id
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/purchase/{request_id}/attachments")
async def upload_purchase_attachment_api(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    from app.services.procurement.purchase_request_service import (
        upload_purchase_request_attachment,
    )

    try:
        return await upload_purchase_request_attachment(
            db, request_id=request_id, user=user, file=file
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/purchase/{request_id}/invoice")
async def upload_purchase_invoice_api(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    from app.services.procurement.invoice_service import upload_purchase_invoice

    try:
        return await upload_purchase_invoice(db, request_id=request_id, user=user, file=file)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/purchase/{request_id}/invoice")
def list_purchase_invoice_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW, *PROCUREMENT_READ)),
):
    from app.services.procurement.invoice_service import list_purchase_invoices
    from app.services.purchase_request_list_scope import user_can_access_purchase_request
    from app.services.permission import user_has_permission_db

    if not user_has_permission_db(db, user.id, "procurement.read"):
        if not user_can_access_purchase_request(db, user, request_id):
            raise HTTPException(status_code=403, detail="access denied")
    return {"items": list_purchase_invoices(db, request_id)}


@router.post("/purchase/{request_id}/mark-invoice-paid")
def mark_invoice_paid_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE, "workflow.approve")),
):
    from app.services.procurement.invoice_service import mark_invoice_paid

    try:
        return mark_invoice_paid(db, request_id=request_id, user=user)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/purchase/{request_id}/payment")
def create_procurement_payment_api(
    request_id: int,
    payload: CreateProcurementPaymentInput,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE, *PAYMENT_WRITE)),
):
    try:
        return create_procurement_payment(
            db,
            request_id=request_id,
            user_id=user.id,
            counterparty_id=payload.counterparty_id,
            counterparty_bank_account_id=payload.counterparty_bank_account_id,
            payer_company_account_id=payload.payer_company_account_id,
            payment_method=payload.payment_method,
            payment_date=payload.payment_date,
            notes=payload.notes,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/purchase/{request_id}/purchase-order")
def ensure_purchase_order_api(
    request_id: int,
    supplier_id: int = Query(..., alias="supplierId"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        po = ensure_purchase_order_for_request(db, request_id, supplier_id)
        from app.services.procurement.purchase_order_service import serialize_purchase_order

        return serialize_purchase_order(db, po)
    except ValueError as err:
        raise_from_value_error(err)


def submit_proforma_api(
    request_id: int,
    proforma_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return submit_proforma_for_approval(
            db, request_id=request_id, proforma_id=proforma_id, user_id=user.id
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/")
def create_request_api(
    payload: CreateRequestInput,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    return create_request(
        db=db,
        user_id=user.id,
        warehouse_id=payload.warehouse_id,
        items=payload.items,
        assignees_by_order=payload.assignees_by_order,
    )


@router.get("/")
def list_requests_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    offset = (page - 1) * page_size
    items = list_requests(
        db,
        requester_id=user.id,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    total = count_requests(
        db,
        requester_id=user.id,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{request_id}")
def get_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_READ)),
):
    req = get_request(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")
    return req


@router.put("/{request_id}")
@router.patch("/{request_id}")
def update_request_api(
    request_id: int,
    payload: UpdateRequestInput,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        return update_request(db, request_id, payload, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PROCUREMENT_WRITE)),
):
    try:
        delete_request(db, request_id, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)
