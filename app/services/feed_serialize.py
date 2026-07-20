"""سریال‌سازی آیتم‌های کارتابل و اعلان برای فرانت."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.inbox import InboxItem
from app.models.notification import Notification
from app.services.workflow_feed_context import (
    WorkflowNotifyContext,
    batch_load_workflow_contexts,
    context_to_meta,
    datetime_to_iso_utc,
    inbox_message_for_step,
    inbox_title_for_step,
    notification_message_for_step,
    notification_title_for_step,
)


_STEP_RE = re.compile(r"مرحله\s+(\d+)")


def _parse_step_order(title: str | None) -> int | None:
    if not title:
        return None
    m = _STEP_RE.search(title)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _workflow_extra_from_context(
    ctx: WorkflowNotifyContext,
    workflow_instance_id: int,
    *,
    for_inbox: bool,
    step_order: int | None,
) -> dict:
    extra = context_to_meta(ctx, workflow_instance_id)
    if for_inbox:
        extra["title"] = inbox_title_for_step(ctx=ctx, step_order=step_order)
        extra["message"] = inbox_message_for_step(ctx=ctx, step_order=step_order)
    else:
        extra["title"] = notification_title_for_step(ctx=ctx)
        extra["message"] = notification_message_for_step(ctx=ctx, step_order=step_order)
    return extra


def _collect_workflow_step_orders(items: list) -> dict[int, int | None]:
    step_orders: dict[int, int | None] = {}
    for item in items:
        ref_type = getattr(item, "ref_type", None)
        ref_id = getattr(item, "ref_id", None)
        if ref_type == "workflow" and ref_id:
            step_orders[int(ref_id)] = _parse_step_order(getattr(item, "title", None))
    return step_orders


def serialize_inbox_items(
    db: Session,
    items: list[InboxItem],
    *,
    enrich: bool = True,
) -> list[dict]:
    if not items:
        return []
    contexts: dict[int, WorkflowNotifyContext] = {}
    if enrich:
        step_orders = _collect_workflow_step_orders(items)
        wf_ids = list(step_orders.keys())
        contexts = batch_load_workflow_contexts(db, wf_ids, step_orders=step_orders)

    out: list[dict] = []
    for item in items:
        step_order = _parse_step_order(item.title)
        payload: dict = {
            "id": item.id,
            "user_id": item.user_id,
            "role_id": item.role_id,
            "title": item.title,
            "message": item.message,
            "ref_id": item.ref_id,
            "ref_type": item.ref_type,
            "is_read": item.is_read,
            "is_done": item.is_done,
            "created_at": datetime_to_iso_utc(item.created_at),
            "read_at": datetime_to_iso_utc(item.read_at),
        }
        if enrich and item.ref_type == "workflow" and item.ref_id:
            ctx = contexts.get(int(item.ref_id))
            if ctx:
                extra = _workflow_extra_from_context(
                    ctx, int(item.ref_id), for_inbox=True, step_order=step_order
                )
                if extra.get("title"):
                    payload["title"] = extra["title"]
                if extra.get("message"):
                    payload["message"] = extra["message"]
                payload.update(
                    {
                        "workflow_instance_id": extra.get("workflowInstanceId"),
                        "request_type_label": extra.get("requestTypeLabel"),
                        "request_title": extra.get("requestTitle"),
                        "request_created_at": extra.get("requestCreatedAt"),
                        "request_amount": extra.get("requestAmount"),
                        "requester_name": extra.get("requesterName"),
                        "business_ref_type": extra.get("businessRefType"),
                        "business_ref_id": extra.get("businessRefId"),
                    }
                )
        out.append(payload)
    return out


def serialize_notification_items(
    db: Session,
    rows: list[Notification],
    *,
    enrich: bool = True,
) -> list[dict]:
    if not rows:
        return []
    contexts: dict[int, WorkflowNotifyContext] = {}
    if enrich:
        step_orders = _collect_workflow_step_orders(rows)
        wf_ids = list(step_orders.keys())
        contexts = batch_load_workflow_contexts(db, wf_ids, step_orders=step_orders)

    out: list[dict] = []
    for row in rows:
        payload: dict = {
            "id": row.id,
            "title": row.title,
            "message": row.message,
            "type": row.type,
            "ref_id": row.ref_id,
            "ref_type": row.ref_type,
            "is_read": row.is_read,
            "created_at": datetime_to_iso_utc(row.created_at),
        }
        if enrich and row.ref_type == "workflow" and row.ref_id:
            ctx = contexts.get(int(row.ref_id))
            if ctx:
                extra = _workflow_extra_from_context(
                    ctx, int(row.ref_id), for_inbox=False, step_order=None
                )
                if extra.get("title"):
                    payload["title"] = extra["title"]
                if extra.get("message"):
                    payload["message"] = extra["message"]
                payload.update(
                    {
                        "workflow_instance_id": extra.get("workflowInstanceId"),
                        "request_type_label": extra.get("requestTypeLabel"),
                        "request_title": extra.get("requestTitle"),
                        "request_created_at": extra.get("requestCreatedAt"),
                        "request_amount": extra.get("requestAmount"),
                        "requester_name": extra.get("requesterName"),
                        "business_ref_type": extra.get("businessRefType"),
                        "business_ref_id": extra.get("businessRefId"),
                    }
                )
        out.append(payload)
    return out


def serialize_inbox_item(db: Session, item: InboxItem, *, enrich: bool = True) -> dict:
    return serialize_inbox_items(db, [item], enrich=enrich)[0]


def serialize_notification_item(db: Session, row: Notification, *, enrich: bool = True) -> dict:
    return serialize_notification_items(db, [row], enrich=enrich)[0]
