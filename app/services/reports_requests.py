"""گزارش سراسری درخواست‌های دارای گردش‌کار + خروجی اکسل."""

from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.models.financial_document import FinancialDocument
from app.models.mission_request import MissionRequest
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.request import Request
from app.models.user import User
from app.models.warehouse_form import WarehouseForm
from app.models.workflow_form import WorkflowForm
from app.models.workflow_instance import WorkflowInstance
from app.services.request_title import user_display_name
from app.services.workflow_feed_context import PAYMENT_TYPE_LABELS
from app.services.workflow_messages import REF_TYPE_LABELS, ref_type_label


def _period_bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(date_from, time.min) if date_from else None
    end = datetime.combine(date_to, time.max) if date_to else None
    return start, end


def _in_period(
    event_at: datetime | None,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    if event_at is None:
        return start is None and end is None
    if start and event_at < start:
        return False
    if end and event_at > end:
        return False
    return True


def _detail_label(ref_type: str, entity: Any | None) -> str:
    base = ref_type_label(ref_type)
    if not entity:
        return base
    if ref_type in ("payment_request", "payment_order"):
        pt = (getattr(entity, "payment_type", None) or "").strip().lower()
        if ref_type == "payment_order":
            kind = (getattr(entity, "payment_order_kind", None) or "individual").strip().lower()
            return "دستور پرداخت جمعی" if kind == "collective" else "دستور پرداخت انفرادی"
        return PAYMENT_TYPE_LABELS.get(pt, base)
    return base


def _load_entity(db: Session, ref_type: str, ref_id: int) -> Any | None:
    rt = (ref_type or "").strip()
    if rt in ("payment_request", "payment_order"):
        return db.get(PaymentRequest, ref_id)
    if rt in ("petty_cash", "petty_cash_settlement"):
        return db.get(PettyCashRequest, ref_id)
    if rt in ("mission_request", "mission_report"):
        return db.get(MissionRequest, ref_id)
    if rt == "financial_document":
        return db.get(FinancialDocument, ref_id)
    if rt in ("purchase_request", "request", "procurement"):
        return db.get(Request, ref_id)
    if rt == "warehouse_form":
        return db.get(WarehouseForm, ref_id)
    if rt == "workflow_form":
        return db.get(WorkflowForm, ref_id)
    return None


def _entity_fields(entity: Any | None) -> tuple[str | None, int | None, str | None, datetime | None]:
    """title, requester_id, entity_status, created_at"""
    if entity is None:
        return None, None, None, None
    title = getattr(entity, "title", None)
    title_s = str(title).strip() if title else None
    requester_id = getattr(entity, "requester_id", None)
    status = getattr(entity, "status", None)
    created_at = getattr(entity, "created_at", None)
    return title_s, requester_id, status, created_at


def list_request_report_types() -> list[dict]:
    """انواع قابل فیلتر در گزارش."""
    items = []
    for key, label in sorted(REF_TYPE_LABELS.items(), key=lambda x: x[1]):
        items.append({"refType": key, "label": label})
    for key, label in PAYMENT_TYPE_LABELS.items():
        items.append({"refType": key, "label": label})
    return items


def get_requests_report(
    db: Session,
    *,
    ref_type: str | None = None,
    requester_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    start, end = _period_bounds(date_from, date_to)
    q = db.query(WorkflowInstance).order_by(WorkflowInstance.id.desc())

    rt_filter = (ref_type or "").strip() or None
    # loan/advance فیلتر روی payment_type است نه ref_type نمونه
    payment_type_filter: str | None = None
    if rt_filter in PAYMENT_TYPE_LABELS:
        payment_type_filter = rt_filter
        q = q.filter(WorkflowInstance.ref_type.in_(("payment_request", "payment_order")))
    elif rt_filter:
        q = q.filter(WorkflowInstance.ref_type == rt_filter)

    instances = q.all()
    user_cache: dict[int, User | None] = {}
    rows: list[dict] = []

    for inst in instances:
        entity = _load_entity(db, inst.ref_type or "", int(inst.ref_id)) if inst.ref_id else None
        title, ent_requester_id, ent_status, created_at = _entity_fields(entity)

        if payment_type_filter and entity is not None:
            pt = (getattr(entity, "payment_type", None) or "").strip().lower()
            if pt != payment_type_filter:
                continue

        if requester_id is not None and ent_requester_id != requester_id:
            continue

        event_at = created_at
        if not _in_period(event_at, start, end):
            continue

        rid = ent_requester_id
        if rid and rid not in user_cache:
            user_cache[rid] = db.get(User, rid)
        requester_name = user_display_name(user_cache.get(rid)) if rid else None

        rows.append(
            {
                "title": title,
                "refType": (inst.ref_type or "").strip(),
                "refTypeLabel": _detail_label(inst.ref_type or "", entity),
                "refId": inst.ref_id,
                "requesterId": rid,
                "requesterName": requester_name,
                "entityStatus": ent_status,
                "workflowStatus": inst.status,
                "createdAt": event_at.isoformat() if event_at else None,
                "_created_at": event_at,
                "workflowInstanceId": inst.id,
            }
        )

    # تازه‌ترین درخواست‌ها بالا
    rows.sort(
        key=lambda r: (
            r.get("_created_at") is not None,
            r.get("_created_at") or datetime.min,
            r.get("workflowInstanceId") or 0,
        ),
        reverse=True,
    )
    for r in rows:
        r.pop("_created_at", None)

    total = len(rows)
    page_items = rows[offset : offset + limit]
    return {
        "items": page_items,
        "total": total,
        "page": (offset // limit) + 1 if limit else 1,
        "pageSize": limit,
    }


def export_requests_report_excel(
    db: Session,
    *,
    ref_type: str | None = None,
    requester_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> bytes:
    data = get_requests_report(
        db,
        ref_type=ref_type,
        requester_id=requester_id,
        date_from=date_from,
        date_to=date_to,
        offset=0,
        limit=50_000,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "درخواست‌ها"
    headers = [
        "عنوان",
        "نوع",
        "برچسب نوع",
        "شناسه",
        "شناسه درخواست‌دهنده",
        "نام درخواست‌دهنده",
        "وضعیت درخواست",
        "وضعیت گردش‌کار",
        "تاریخ ثبت",
        "شناسه نمونه گردش‌کار",
    ]
    ws.append(headers)
    for item in data["items"]:
        ws.append(
            [
                item.get("title") or "",
                item.get("refType") or "",
                item.get("refTypeLabel") or "",
                item.get("refId"),
                item.get("requesterId"),
                item.get("requesterName") or "",
                item.get("entityStatus") or "",
                item.get("workflowStatus") or "",
                item.get("createdAt") or "",
                item.get("workflowInstanceId"),
            ]
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
