from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import PAYMENT_ACCESS, PAYMENT_WRITE
from app.dependencies.auth import require_any_permission, require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.models.financial_document import FinancialDocument
from app.schemas.attachment import AttachmentOut
from app.schemas.financial_document import (
    FinancialDocumentCreate,
    FinancialDocumentListResponse,
    FinancialDocumentOut,
)
from app.services import financial_document as fd_svc
from app.services.attachment_service import (
    ENTITY_FINANCIAL_DOCUMENT,
    delete_entity_attachment,
    list_attachments_serialized,
    save_entity_attachment,
)

router = APIRouter(prefix="/financial-documents", tags=["Financial documents"])


@router.post("/", response_model=FinancialDocumentOut, status_code=status.HTTP_201_CREATED)
def create_financial_document_api(
    payload: FinancialDocumentCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        return fd_svc.create_financial_document(
            db,
            user,
            document_type=payload.document_type,
            title=payload.title,
            description=payload.description,
            amount=float(payload.amount) if payload.amount is not None else None,
            document_date=payload.document_date,
            check_number=payload.check_number,
            party_name=payload.party_name,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/list-capabilities")
def financial_document_list_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    return fd_svc.get_list_capabilities(db, user)


@router.get("/", response_model=FinancialDocumentListResponse)
def list_financial_documents_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    scope: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        offset = (page - 1) * page_size
        items = fd_svc.list_financial_documents(
            db,
            viewer=user,
            scope=scope,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search,
        )
        total = fd_svc.count_financial_documents(db, viewer=user, scope=scope, search=search)
    except ValueError as err:
        raise_from_value_error(err)
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/by-workflow-instance/{instance_id}", response_model=FinancialDocumentOut)
def get_by_workflow_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return fd_svc.get_financial_document_by_workflow_instance(db, instance_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{document_id}", response_model=FinancialDocumentOut)
def get_financial_document_api(
    document_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return fd_svc.get_financial_document(db, document_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_financial_document_api(
    document_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        fd_svc.delete_financial_document(db, document_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{document_id}/attachments", response_model=list[AttachmentOut])
def list_attachments_api(
    document_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        fd_svc.get_financial_document(db, document_id, user)
    except ValueError as err:
        raise_from_value_error(err)
    return list_attachments_serialized(db, ENTITY_FINANCIAL_DOCUMENT, document_id)


@router.post(
    "/{document_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment_api(
    document_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        entity = db.get(FinancialDocument, document_id)
        if not entity:
            raise ValueError("سند مالی یافت نشد")
        if entity.requester_id != user.id:
            raise ValueError("فقط ثبت‌کننده می‌تواند پیوست بارگذاری کند")
        if entity.status != "pending":
            raise ValueError("پس از شروع تأیید، افزودن پیوست مجاز نیست")
        att = await save_entity_attachment(
            db, ENTITY_FINANCIAL_DOCUMENT, document_id, file, uploader_id=user.id
        )
        return att
    except ValueError as err:
        raise_from_value_error(err)


@router.delete(
    "/{document_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment_api(
    document_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        entity = db.get(FinancialDocument, document_id)
        if not entity or entity.requester_id != user.id:
            raise ValueError("access denied")
        delete_entity_attachment(db, attachment_id, user_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)
