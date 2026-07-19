from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.api_error import api_error_detail
from app.constants.api_permissions import WORKFLOW_APPROVE, WORKFLOW_VIEW
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.workflow import WorkflowApproveRequest, WorkflowRejectRequest
from app.services.workflow import approve_step, reject_step
from app.services.workflow_step_attachment import (
    list_instance_step_attachments,
    upload_step_attachment,
)
from app.services.workflow_instance_list import (
    count_workflow_instances,
    get_workflow_instance_for_viewer,
    list_workflow_instance_scopes,
    list_workflow_instances,
)
from app.services.related_requests import (
    get_related_requests,
    get_related_requests_for_instance,
)
from app.services.workflow_instance_query import (
    get_approval_history_for_instance,
    get_instance_approval_plan,
)

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/instances/list-capabilities")
def workflow_instances_list_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    return {"scopes": list_workflow_instance_scopes(db, user)}


@router.get("/instances")
def list_workflow_instances_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    scope: str | None = Query(None),
    ref_type: str | None = Query(None, alias="refType"),
    status: str | None = Query(None),
    instance_id: int | None = Query(None, alias="id"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    try:
        offset = (page - 1) * page_size
        inst_id = int(instance_id) if instance_id is not None else None
        items = list_workflow_instances(
            db,
            viewer=user,
            scope=scope,
            ref_type=ref_type,
            status=status,
            instance_id=inst_id,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search,
        )
        total = count_workflow_instances(
            db,
            viewer=user,
            scope=scope,
            ref_type=ref_type,
            status=status,
            instance_id=inst_id,
            search=search,
        )
    except ValueError as err:
        raise_from_value_error(err)
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/instances/{instance_id}")
def get_workflow_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    data = get_workflow_instance_for_viewer(db, viewer=user, instance_id=instance_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error_detail(
                "WORKFLOW_INSTANCE_NOT_FOUND",
                "نمونه گردش‌کار یافت نشد یا دسترسی ندارید",
            ),
        )
    return data


@router.get("/instances/{instance_id}/related")
def get_related_requests_for_instance_api(
    instance_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    del user
    data = get_related_requests_for_instance(db, instance_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error_detail("NOT_FOUND", "درخواست مرتبط یافت نشد"),
        )
    return data.to_dict()


@router.get("/related")
def get_related_requests_api(
    ref_type: str = Query(..., alias="refType"),
    ref_id: int = Query(..., alias="refId", ge=1),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    del user
    data = get_related_requests(db, ref_type=ref_type, ref_id=ref_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error_detail("NOT_FOUND", "درخواست مرتبط یافت نشد"),
        )
    return data.to_dict()


@router.get("/instances/{instance_id}/approval-plan")
def get_approval_plan(
    instance_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    del _user
    data = get_instance_approval_plan(db, instance_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error_detail("WORKFLOW_INSTANCE_NOT_FOUND", "workflow instance not found"),
        )
    return data


@router.get("/instances/{instance_id}/approval-history")
def get_approval_history(
    instance_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    del _user
    data = get_approval_history_for_instance(db, instance_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error_detail("WORKFLOW_INSTANCE_NOT_FOUND", "workflow instance not found"),
        )
    return data


@router.post("/{instance_id}/approve")
def approve(
    instance_id: int,
    body: WorkflowApproveRequest | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_APPROVE)),
):
    payload = body or WorkflowApproveRequest()
    try:
        return approve_step(
            db,
            instance_id,
            user,
            comment=payload.comment,
            amount=payload.amount,
            payment_date=payload.payment_date,
            installment_count=payload.installment_count,
            first_installment_date=payload.first_installment_date,
            settlement_date=payload.settlement_date,
            payer_company_account_id=payload.payer_company_account_id,
            payer_account=payload.payer_account,
            payment_method=payload.payment_method,
            payment_location=payload.payment_location,
            check_plan=payload.check_plan,
            payment_executed=payload.payment_executed,
            sepidar_confirmed=payload.sepidar_confirmed,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{instance_id}/reject")
def reject(
    instance_id: int,
    body: WorkflowRejectRequest,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_APPROVE)),
):
    try:
        return reject_step(
            db,
            instance_id,
            user,
            comment=body.comment,
            return_to=body.return_to,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/instances/{instance_id}/step-attachments")
def list_step_attachments_api(
    instance_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_VIEW)),
):
    from app.services.workflow_step_attachment import collect_plan_attachments

    return {"items": collect_plan_attachments(db, instance_id)}


@router.post("/instances/{instance_id}/steps/{step_id}/attachments")
async def upload_step_attachment_api(
    instance_id: int,
    step_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_APPROVE)),
):
    return upload_step_attachment(
        db,
        instance_id=instance_id,
        step_id=step_id,
        user=user,
        file=file,
    )
