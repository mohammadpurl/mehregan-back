from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import PAYMENT_ACCESS, PAYMENT_WRITE
from app.dependencies.auth import require_any_permission, require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.schemas.attachment import AttachmentOut
from app.schemas.mission_request import (
    MissionReportSubmit,
    MissionRequestCreate,
    MissionRequestListResponse,
    MissionRequestOut,
)
from app.services import mission_request as mr_svc
from app.services.attachment_service import (
    ENTITY_MISSION_REQUEST,
    delete_entity_attachment,
    list_attachments_serialized,
    save_entity_attachment,
    serialize_attachment,
)

router = APIRouter(prefix="/mission-requests", tags=["Mission requests"])


@router.post("/", response_model=MissionRequestOut, status_code=status.HTTP_201_CREATED)
def create_mission_request_api(
    payload: MissionRequestCreate,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        return mr_svc.create_mission_request(
            db,
            user.id,
            destination=payload.destination,
            reason=payload.reason,
            vehicle=payload.vehicle,
            title=payload.title,
            assignees_by_order=payload.assignees_by_order,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/list-capabilities")
def mission_request_list_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    return mr_svc.get_mission_request_list_capabilities(db, user)


@router.get("/", response_model=MissionRequestListResponse)
def list_mission_requests_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    scope: str | None = Query(None, description="mine | team | all | approver | participated"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        offset = (page - 1) * page_size
        items = mr_svc.list_mission_requests(
            db,
            viewer=user,
            scope=scope,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search,
        )
        total = mr_svc.count_mission_requests(
            db, viewer=user, scope=scope, search=search
        )
    except ValueError as err:
        raise_from_value_error(err)
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/by-workflow-instance/{instance_id}", response_model=MissionRequestOut)
def get_mission_by_workflow_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return mr_svc.get_mission_request_by_workflow_instance(db, instance_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{request_id}", response_model=MissionRequestOut)
def get_mission_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        return mr_svc.get_mission_request(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{request_id}/report", response_model=MissionRequestOut)
def submit_mission_report_api(
    request_id: int,
    payload: MissionReportSubmit,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        return mr_svc.submit_mission_report(
            db,
            request_id,
            user.id,
            report_text=payload.report_text,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mission_request_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_permission("payment.create")),
):
    try:
        mr_svc.delete_mission_request(db, request_id, user.id)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{request_id}/attachments", response_model=list[AttachmentOut])
def list_mission_attachments_api(
    request_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_ACCESS)),
):
    try:
        mr_svc.get_mission_request(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)
    return list_attachments_serialized(db, ENTITY_MISSION_REQUEST, request_id)


@router.post(
    "/{request_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_mission_attachment_api(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        detail = mr_svc.get_mission_request(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)
    if detail.get("requester_id") != user.id:
        from app.services.workflow_lock import user_may_bypass_workflow_edit_lock

        if not user_may_bypass_workflow_edit_lock(user):
            raise_from_value_error(ValueError("فقط درخواست‌دهنده می‌تواند پیوست بارگذاری کند"))
    row = await save_entity_attachment(
        db,
        entity_type=ENTITY_MISSION_REQUEST,
        entity_id=request_id,
        uploaded_by_id=user.id,
        file=file,
    )
    db.commit()
    return serialize_attachment(row)


@router.delete(
    "/{request_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_mission_attachment_api(
    request_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*PAYMENT_WRITE)),
):
    try:
        detail = mr_svc.get_mission_request(db, request_id, user)
    except ValueError as err:
        raise_from_value_error(err)
    if detail.get("requester_id") != user.id:
        from app.services.workflow_lock import user_may_bypass_workflow_edit_lock

        if not user_may_bypass_workflow_edit_lock(user):
            raise_from_value_error(ValueError("فقط درخواست‌دهنده می‌تواند پیوست را حذف کند"))
    if not delete_entity_attachment(
        db,
        entity_type=ENTITY_MISSION_REQUEST,
        entity_id=request_id,
        attachment_id=attachment_id,
    ):
        raise_from_value_error(ValueError("پیوست یافت نشد"))
