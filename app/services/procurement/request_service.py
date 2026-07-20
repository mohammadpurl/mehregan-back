from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.messaging.publisher import publish_event
from app.models.request import Request
from app.models.request_item import RequestItem
from app.schemas.request import RequestItemInput, UpdateRequestInput
from app.constants.procurement import PURCHASE_WORKFLOW_REFS
from app.services.crud_utils import ensure_editable
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort
from app.services.workflow_cleanup import (
    cancel_workflows_for_refs,
    ensure_request_deletable,
)


def create_request(
    db: Session,
    user_id: int,
    warehouse_id: int,
    items: list[RequestItemInput],
    assignees_by_order: dict[str, int] | None = None,
):
    request = Request(
        requester_id=user_id,
        warehouse_id=warehouse_id,
        status="pending",
    )
    db.add(request)
    db.flush()

    for item in items:
        ri = RequestItem(
            request_id=request.id,
            item_id=item.item_id,
            quantity=item.quantity,
        )
        db.add(ri)

    db.commit()
    db.refresh(request)

    wf_payload: dict = {
        "ref_type": "request",
        "ref_id": request.id,
        "submitter_id": user_id,
    }
    if assignees_by_order:
        wf_payload["assignees_by_order"] = assignees_by_order
    publish_event("workflow.start", wf_payload)
    return request


def get_request(db: Session, request_id: int) -> Request | None:
    return db.get(Request, request_id)


def list_requests(
    db: Session,
    requester_id: int | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
):
    query = db.query(Request)
    if requester_id:
        query = query.filter(Request.requester_id == requester_id)
    query = apply_equal_filter(query, Request, filter_by, filter_value)
    query = apply_search_filter(query, Request, search, ["status", "type"])
    query = apply_sort(query, Request, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_requests(
    db: Session,
    requester_id: int | None = None,
    filter_by: str | None = None,
    filter_value: str | None = None,
    search: str | None = None,
) -> int:
    query = db.query(func.count(Request.id))
    if requester_id:
        query = query.filter(Request.requester_id == requester_id)
    query = apply_equal_filter(query, Request, filter_by, filter_value)
    query = apply_search_filter(query, Request, search, ["status", "type"])
    return query.scalar() or 0


def update_request(
    db: Session,
    request_id: int,
    payload: UpdateRequestInput,
    *,
    requester_id: int | None = None,
) -> Request:
    request = db.get(Request, request_id)
    if not request:
        raise ValueError("request not found")
    if requester_id is not None and request.requester_id != requester_id:
        raise ValueError("access denied")
    ensure_editable(request)

    if payload.warehouse_id is not None:
        request.warehouse_id = payload.warehouse_id
    if payload.items is not None:
        db.query(RequestItem).filter_by(request_id=request_id).delete()
        for item in payload.items:
            db.add(
                RequestItem(
                    request_id=request_id,
                    item_id=item.item_id,
                    quantity=item.quantity,
                )
            )
    db.commit()
    db.refresh(request)
    return request


def delete_request(
    db: Session, request_id: int, *, requester_id: int | None = None
) -> None:
    request = db.get(Request, request_id)
    if not request:
        raise ValueError("request not found")
    if requester_id is not None and request.requester_id != requester_id:
        raise ValueError("access denied")
    ensure_editable(request)
    ensure_request_deletable(db, ref_types=PURCHASE_WORKFLOW_REFS, ref_id=request_id)
    cancel_workflows_for_refs(db, PURCHASE_WORKFLOW_REFS, request_id)
    db.query(RequestItem).filter_by(request_id=request_id).delete()
    db.delete(request)
    db.commit()
