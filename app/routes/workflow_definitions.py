from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import WORKFLOW_READ
from app.dependencies.auth import require_any_permission, require_permission
from app.services.permission import user_has_permission_db
from app.dependencies.pagination import ListQueryParams, get_list_params, paginated_response
from app.schemas.workflow_definition import (
    WorkflowAssigneePreview,
    WorkflowAssigneePreviewRequest,
    WorkflowDefinitionUpsert,
)
from app.services import workflow_definition_service as wfdef_svc

router = APIRouter(prefix="/workflow-definitions", tags=["Workflow definitions"])


def _guard_preview_submitter(db: Session, user, submitter_id: int) -> None:
    if submitter_id != user.id and not user_has_permission_db(db, user.id, "admin.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط برای ثبت‌کننده خود یا ادمین مجاز است",
        )


@router.get("/")
def list_definitions(
    params: ListQueryParams = Depends(get_list_params),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    items = wfdef_svc.list_definitions(
        db,
        offset=params.offset,
        limit=params.page_size,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
        search=params.search,
    )
    total = wfdef_svc.count_definitions(db, search=params.search)
    return paginated_response(items, total, params)


@router.get("/{ref_type}/assignees-preview", response_model=list[WorkflowAssigneePreview])
def preview_assignees(
    ref_type: str,
    submitter_id: int = Query(..., alias="submitterId"),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    """پیش‌نمایش تأییدکنندگان هر مرحله برای یک ثبت‌کننده (از تعریف ذخیره‌شده)."""
    _guard_preview_submitter(db, user, submitter_id)
    return wfdef_svc.preview_assignees(db, ref_type, submitter_id=submitter_id)


@router.post("/{ref_type}/assignees-preview", response_model=list[WorkflowAssigneePreview])
def preview_assignees_draft(
    ref_type: str,
    payload: WorkflowAssigneePreviewRequest,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    """پیش‌نمایش روی پیش‌نویس مراحل فرم ادمین (قبل از ذخیره)."""
    _guard_preview_submitter(db, user, payload.submitter_id)
    try:
        return wfdef_svc.preview_assignees(
            db,
            ref_type,
            submitter_id=payload.submitter_id,
            steps_override=payload.steps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{ref_type}")
def get_definition(
    ref_type: str,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    row = wfdef_svc.get_definition_by_ref_type(db, ref_type)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="definition not found")
    return row


@router.put("/{ref_type}")
def upsert_definition(
    ref_type: str,
    payload: WorkflowDefinitionUpsert,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if payload.ref_type != ref_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ref_type in path and body must match",
        )
    steps_payload = [s.model_dump() for s in payload.steps]
    try:
        return wfdef_svc.upsert_definition(
            db,
            ref_type=payload.ref_type,
            name=payload.name,
            steps=steps_payload,
            code=payload.code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{ref_type}", status_code=status.HTTP_204_NO_CONTENT)
def delete_definition(
    ref_type: str,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if not wfdef_svc.delete_definition(db, ref_type):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="definition not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
