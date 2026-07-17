from sqlalchemy.orm import Session
from sqlalchemy import func

from app.infrastructure.messaging.publisher import publish_event
from app.models.workflow_form import WorkflowForm
from app.schemas.forms import WorkflowFormUpdate
from app.services.crud_utils import ensure_editable
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort
from app.services.workflow_cleanup import (
    cancel_workflow_for_ref,
    ensure_request_deletable,
)


def create_workflow_form(
    db: Session,
    requester_id: int,
    receiver_id: int,
    title: str,
    description: str | None,
):
    form = WorkflowForm(
        requester_id=requester_id,
        receiver_id=receiver_id,
        title=title,
        description=description,
        status="pending",
    )
    db.add(form)
    db.commit()
    db.refresh(form)

    publish_event(
        "workflow.start",
        {
            "ref_type": "workflow_form",
            "ref_id": form.id,
            "submitter_id": requester_id,
            "user_id": receiver_id,
        },
    )
    return form


def list_workflow_forms(
    db: Session,
    requester_id: int | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(WorkflowForm)
    if requester_id:
        query = query.filter(WorkflowForm.requester_id == requester_id)
    query = apply_equal_filter(query, WorkflowForm, filter_by, filter_value)
    query = apply_search_filter(query, WorkflowForm, search, ["title", "description", "status"])
    query = apply_sort(query, WorkflowForm, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_workflow_forms(
    db: Session,
    requester_id: int | None = None,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(WorkflowForm.id))
    if requester_id:
        query = query.filter(WorkflowForm.requester_id == requester_id)
    query = apply_equal_filter(query, WorkflowForm, filter_by, filter_value)
    query = apply_search_filter(query, WorkflowForm, search, ["title", "description", "status"])
    return query.scalar() or 0


def get_workflow_form(db: Session, form_id: int) -> WorkflowForm | None:
    return db.get(WorkflowForm, form_id)


def update_workflow_form(
    db: Session,
    form_id: int,
    payload: WorkflowFormUpdate,
    *,
    requester_id: int | None = None,
) -> WorkflowForm:
    form = db.get(WorkflowForm, form_id)
    if not form:
        raise ValueError("workflow form not found")
    if requester_id is not None and form.requester_id != requester_id:
        raise ValueError("access denied")
    ensure_editable(form)
    if payload.receiver_id is not None:
        form.receiver_id = payload.receiver_id
    if payload.title is not None:
        form.title = payload.title
    if payload.description is not None:
        form.description = payload.description
    db.commit()
    db.refresh(form)
    return form


def delete_workflow_form(
    db: Session, form_id: int, *, requester_id: int | None = None
) -> None:
    form = db.get(WorkflowForm, form_id)
    if not form:
        raise ValueError("workflow form not found")
    if requester_id is not None and form.requester_id != requester_id:
        raise ValueError("access denied")
    ensure_editable(form)
    ensure_request_deletable(db, ref_types="workflow_form", ref_id=form_id)
    cancel_workflow_for_ref(db, "workflow_form", form_id)
    db.delete(form)
    db.commit()
