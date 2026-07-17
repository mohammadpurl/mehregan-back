from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.messaging.publisher import publish_event
from app.models.warehouse_form import WarehouseForm
from app.schemas.forms import WarehouseFormUpdate
from app.services.crud_utils import ensure_editable
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort
from app.services.workflow_cleanup import (
    cancel_workflow_for_ref,
    ensure_request_deletable,
)


def create_warehouse_form(
    db: Session,
    requester_id: int,
    form_type: str,
    source: str | None,
    destination: str | None,
    receiver_name: str | None,
    effective_date: date | None,
    description: str | None,
    assignees_by_order: dict[str, int] | None = None,
):
    resolved_effective_date = effective_date
    if isinstance(effective_date, str) and effective_date:
        resolved_effective_date = date.fromisoformat(effective_date)

    form = WarehouseForm(
        requester_id=requester_id,
        form_type=form_type,
        source=source,
        destination=destination,
        receiver_name=receiver_name,
        effective_date=resolved_effective_date,
        description=description,
        status="PENDING",
    )
    db.add(form)
    db.commit()
    db.refresh(form)

    wf_payload: dict = {
        "ref_type": "warehouse_form",
        "ref_id": form.id,
        "submitter_id": requester_id,
    }
    if assignees_by_order:
        wf_payload["assignees_by_order"] = assignees_by_order
    publish_event("workflow.start", wf_payload)
    return form


def list_warehouse_forms(
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
    query = db.query(WarehouseForm)
    if requester_id:
        query = query.filter(WarehouseForm.requester_id == requester_id)
    query = apply_equal_filter(query, WarehouseForm, filter_by, filter_value)
    query = apply_search_filter(
        query,
        WarehouseForm,
        search,
        ["form_type", "source", "destination", "receiver_name", "description", "status"],
    )
    query = apply_sort(query, WarehouseForm, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_warehouse_forms(
    db: Session,
    requester_id: int | None = None,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(WarehouseForm.id))
    if requester_id:
        query = query.filter(WarehouseForm.requester_id == requester_id)
    query = apply_equal_filter(query, WarehouseForm, filter_by, filter_value)
    query = apply_search_filter(
        query,
        WarehouseForm,
        search,
        ["form_type", "source", "destination", "receiver_name", "description", "status"],
    )
    return query.scalar() or 0


def get_warehouse_form(db: Session, form_id: int) -> WarehouseForm | None:
    return db.get(WarehouseForm, form_id)


def update_warehouse_form(
    db: Session,
    form_id: int,
    payload: WarehouseFormUpdate,
    *,
    requester_id: int | None = None,
) -> WarehouseForm:
    form = db.get(WarehouseForm, form_id)
    if not form:
        raise ValueError("warehouse form not found")
    if requester_id is not None and form.requester_id != requester_id:
        raise ValueError("access denied")
    ensure_editable(form)
    if payload.form_type is not None:
        form.form_type = payload.form_type
    if payload.source is not None:
        form.source = payload.source
    if payload.destination is not None:
        form.destination = payload.destination
    if payload.receiver_name is not None:
        form.receiver_name = payload.receiver_name
    if payload.effective_date is not None:
        form.effective_date = payload.effective_date
    if payload.description is not None:
        form.description = payload.description
    db.commit()
    db.refresh(form)
    return form


def delete_warehouse_form(
    db: Session, form_id: int, *, requester_id: int | None = None
) -> None:
    form = db.get(WarehouseForm, form_id)
    if not form:
        raise ValueError("warehouse form not found")
    if requester_id is not None and form.requester_id != requester_id:
        raise ValueError("access denied")
    ensure_editable(form)
    ensure_request_deletable(db, ref_types="warehouse_form", ref_id=form_id)
    cancel_workflow_for_ref(db, "warehouse_form", form_id)
    db.delete(form)
    db.commit()
