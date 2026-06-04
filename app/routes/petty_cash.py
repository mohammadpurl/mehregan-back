from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import PAYMENT_ACCESS, PAYMENT_WRITE
from app.dependencies.auth import require_any_permission, require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.schemas.attachment import AttachmentOut
from app.schemas.petty_cash import (
    PettyCashCreate,
    PettyCashEligibilityOut,
    PettyCashExpensesSubmit,
    PettyCashListResponse,
    PettyCashOut,
)
from app.services import petty_cash as pc_svc
from app.services.attachment_service import (
    ENTITY_PETTY_CASH,
    delete_entity_attachment,
    list_attachments_serialized,
    save_entity_attachment,
    serialize_attachment,
)
from app.services.petty_cash import _get_owned_request

router = APIRouter(prefix="/petty-cash", tags=["Petty cash"])


@router.get("/eligibility", response_model=PettyCashEligibilityOut)
def check_eligibility_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    return pc_svc.check_eligibility(db, user.id)


@router.post("/", response_model=PettyCashOut, status_code=status.HTTP_201_CREATED)
def create_petty_cash_api(
    payload: PettyCashCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        return pc_svc.create_petty_cash_request(
            db,
            user.id,
            amount=payload.amount,
            reason=payload.reason,
            requested_date=payload.requested_date,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/list-capabilities")
def petty_cash_list_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    return pc_svc.get_petty_cash_list_capabilities(db, user)


@router.get("/", response_model=PettyCashListResponse)
def list_petty_cash_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
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
        items = pc_svc.list_petty_cash_requests(
            db,
            viewer=user,
            scope=scope,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search,
        )
        total = pc_svc.count_petty_cash_requests(
            db, viewer=user, scope=scope, search=search
        )
    except ValueError as err:
        raise_from_value_error(err)
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get(
    "/{request_id}/attachments",
    response_model=list[AttachmentOut],
)
def list_petty_cash_attachments_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        pc_svc.get_petty_cash(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)
    return list_attachments_serialized(db, ENTITY_PETTY_CASH, request_id)


@router.post(
    "/{request_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_petty_cash_attachment_api(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        _get_owned_request(db, request_id, user.id)
    except ValueError as err:
        raise_from_value_error(err)
    att = await save_entity_attachment(
        db,
        entity_type=ENTITY_PETTY_CASH,
        entity_id=request_id,
        uploaded_by_id=user.id,
        file=file,
    )
    return serialize_attachment(att)


@router.delete(
    "/{request_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_petty_cash_attachment_api(
    request_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        _get_owned_request(db, request_id, user.id)
    except ValueError as err:
        raise_from_value_error(err)
    if not delete_entity_attachment(
        db,
        entity_type=ENTITY_PETTY_CASH,
        entity_id=request_id,
        attachment_id=attachment_id,
    ):
        raise HTTPException(status_code=404, detail="پیوست یافت نشد")


@router.get("/by-workflow-instance/{instance_id}", response_model=PettyCashOut)
def get_petty_cash_by_workflow_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return pc_svc.get_petty_cash_by_workflow_instance(db, instance_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{request_id}", response_model=PettyCashOut)
def get_petty_cash_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return pc_svc.get_petty_cash(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{request_id}/expenses", response_model=PettyCashOut)
def submit_expenses_api(
    request_id: int,
    payload: PettyCashExpensesSubmit,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        return pc_svc.submit_expenses_manual(
            db,
            request_id,
            user.id,
            payload.lines,
            replace_existing=payload.replace_existing,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{request_id}/expenses/import-excel", response_model=PettyCashOut)
async def import_expenses_excel_api(
    request_id: int,
    file: UploadFile = File(...),
    replace_existing: bool = Query(True, alias="replaceExisting"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فقط فایل Excel (.xlsx) پشتیبانی می‌شود",
        )
    content = await file.read()
    try:
        return pc_svc.submit_expenses_excel(
            db,
            request_id,
            user.id,
            content,
            replace_existing=replace_existing,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_petty_cash_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        pc_svc.delete_petty_cash_request(db, request_id, user.id)
    except ValueError as err:
        raise_from_value_error(err)
