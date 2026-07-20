from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import WORKFLOW_READ
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.forms import WorkflowFormCreate, WorkflowFormUpdate
from app.services.workflow_form import (
    count_workflow_forms,
    create_workflow_form,
    delete_workflow_form,
    get_workflow_form,
    list_workflow_forms,
    update_workflow_form,
)

router = APIRouter(prefix="/workflow-forms", tags=["Workflow Forms"])


@router.post("/")
def create_workflow_form_api(
    payload: WorkflowFormCreate,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    return create_workflow_form(
        db=db,
        requester_id=user.id,
        receiver_id=payload.receiver_id,
        title=payload.title,
        description=payload.description,
    )


@router.get("/")
def list_workflow_forms_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("created_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    offset = (page - 1) * page_size
    items = list_workflow_forms(
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
    total = count_workflow_forms(
        db,
        requester_id=user.id,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{form_id}")
def get_workflow_form_api(
    form_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    form = get_workflow_form(db, form_id)
    if not form:
        raise HTTPException(status_code=404, detail="workflow form not found")
    if form.requester_id != user.id and form.receiver_id != user.id:
        from app.models.workflow_instance import WorkflowInstance
        from app.services.workflow_instance_list import user_can_view_workflow_instance

        inst = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.ref_type == "workflow_form",
                WorkflowInstance.ref_id == form_id,
            )
            .order_by(WorkflowInstance.id.desc())
            .first()
        )
        if not inst or not user_can_view_workflow_instance(db, user, inst.id):
            raise HTTPException(status_code=404, detail="workflow form not found")
    return form


@router.put("/{form_id}")
@router.patch("/{form_id}")
def update_workflow_form_api(
    form_id: int,
    payload: WorkflowFormUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    try:
        return update_workflow_form(db, form_id, payload, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_form_api(
    form_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WORKFLOW_READ)),
):
    try:
        delete_workflow_form(db, form_id, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)
