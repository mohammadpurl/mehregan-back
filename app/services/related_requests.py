"""درخواست‌ها و گردش‌کارهای مرتبط با یک موجودیت کسب‌وکار."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants.financial_document import WORKFLOW_REF_FINANCIAL_DOCUMENT
from app.constants.payment_order import WORKFLOW_REF_PAYMENT_ORDER
from app.constants.procurement import (
    PURCHASE_WORKFLOW_REFS,
    REQUEST_TYPE_PURCHASE,
    WORKFLOW_REF_GRN,
)
from app.models.financial_document import FinancialDocument
from app.models.mission_request import MissionRequest
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.procurement.goods_receipt import GoodsReceipt
from app.models.procurement.proforma import ProcurementProforma
from app.models.procurement.purchase_order import PurchaseOrder
from app.models.request import Request
from app.models.workflow_instance import WorkflowInstance
from app.services.workflow_instance_query import REF_TYPE_PHASE_LABELS, ref_type_label_fallback


@dataclass
class RelatedRequestItem:
    ref_type: str
    ref_id: int
    label: str
    title: str
    status: str | None = None
    relation: str = "self"
    workflow_instance_id: int | None = None
    workflow_status: str | None = None
    created_at: datetime | None = None
    link_ref_type: str | None = None
    link_ref_id: int | None = None

    def to_dict(self, *, is_anchor: bool = False) -> dict:
        body = {
            "refType": self.ref_type,
            "refId": self.ref_id,
            "label": self.label,
            "title": self.title,
            "status": self.status,
            "relation": self.relation,
            "workflowInstanceId": self.workflow_instance_id,
            "workflowStatus": self.workflow_status,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "isAnchor": is_anchor,
        }
        if self.link_ref_type and self.link_ref_id:
            body["linkRefType"] = self.link_ref_type
            body["linkRefId"] = self.link_ref_id
        return body


@dataclass
class RelatedRequestsResult:
    anchor_ref_type: str
    anchor_ref_id: int
    anchor_label: str
    items: list[RelatedRequestItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "anchor": {
                "refType": self.anchor_ref_type,
                "refId": self.anchor_ref_id,
                "label": self.anchor_label,
            },
            "items": [
                item.to_dict(is_anchor=item.ref_type == self.anchor_ref_type and item.ref_id == self.anchor_ref_id)
                for item in self.items
            ],
        }


def _label(ref_type: str) -> str:
    return REF_TYPE_PHASE_LABELS.get(ref_type, ref_type_label_fallback(ref_type))


def _latest_workflow(
    db: Session, ref_type: str, ref_id: int
) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == ref_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def _workflows_for_ref_types(
    db: Session, ref_id: int, ref_types: tuple[str, ...]
) -> list[WorkflowInstance]:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_id == ref_id,
            WorkflowInstance.ref_type.in_(ref_types),
        )
        .order_by(WorkflowInstance.id.asc())
        .all()
    )


def _item_from_workflow(
    inst: WorkflowInstance,
    *,
    relation: str,
    title: str | None = None,
    status: str | None = None,
    created_at: datetime | None = None,
) -> RelatedRequestItem:
    return RelatedRequestItem(
        ref_type=inst.ref_type,
        ref_id=inst.ref_id,
        label=_label(inst.ref_type),
        title=title or f"{_label(inst.ref_type)} — گردش‌کار #{inst.id}",
        status=status,
        relation=relation,
        workflow_instance_id=inst.id,
        workflow_status=inst.status,
        created_at=created_at,
    )


def _add_unique(
    bucket: list[RelatedRequestItem],
    seen: set[tuple[str, int, str]],
    item: RelatedRequestItem,
) -> None:
    key = (item.ref_type, item.ref_id, item.relation)
    if key in seen:
        return
    seen.add(key)
    bucket.append(item)


def _collect_purchase_request_chain(
    db: Session, request_id: int, items: list[RelatedRequestItem], seen: set[tuple[str, int, str]]
) -> None:
    req = db.get(Request, request_id)
    if not req or req.type != REQUEST_TYPE_PURCHASE:
        return

    for inst in _workflows_for_ref_types(db, request_id, PURCHASE_WORKFLOW_REFS):
        _add_unique(
            items,
            seen,
            _item_from_workflow(
                inst,
                relation="workflow",
                title=(req.title or "").strip() or f"درخواست خرید #{request_id}",
                status=req.status,
                created_at=req.created_at,
            ),
        )

    if req.payment_request_id:
        pr = db.get(PaymentRequest, req.payment_request_id)
        for wf_ref in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
            inst = _latest_workflow(db, wf_ref, req.payment_request_id)
            if inst:
                _add_unique(
                    items,
                    seen,
                    _item_from_workflow(
                        inst,
                        relation="linked_payment",
                        title=f"پرداخت خرید #{req.payment_request_id}"
                        + (f" — {float(pr.amount):,.0f} ریال" if pr else ""),
                        status=pr.status if pr else None,
                        created_at=pr.created_at if pr else None,
                    ),
                )

    proforma_wf = _latest_workflow(db, "procurement_proforma", request_id)
    for pf in (
        db.query(ProcurementProforma)
        .filter(ProcurementProforma.request_id == request_id)
        .order_by(ProcurementProforma.id.asc())
        .all()
    ):
        _add_unique(
            items,
            seen,
            RelatedRequestItem(
                ref_type="procurement_proforma",
                ref_id=pf.id,
                label="پیش‌فاکتور",
                title=f"پیش‌فاکتور #{pf.id} — {float(pf.amount):,.0f} {pf.currency}",
                status=pf.status,
                relation="proforma",
                workflow_instance_id=proforma_wf.id if proforma_wf else None,
                workflow_status=proforma_wf.status if proforma_wf else None,
                created_at=pf.created_at,
                link_ref_type="purchase_request",
                link_ref_id=request_id,
            ),
        )

    po_ids: set[int] = set()
    if req.purchase_order_id:
        po_ids.add(req.purchase_order_id)
    for po in db.query(PurchaseOrder).filter(PurchaseOrder.request_id == request_id).all():
        po_ids.add(po.id)

    for po_id in sorted(po_ids):
        po = db.get(PurchaseOrder, po_id)
        if not po:
            continue
        _add_unique(
            items,
            seen,
            RelatedRequestItem(
                ref_type="purchase_order",
                ref_id=po.id,
                label="سفارش خرید",
                title=f"سفارش خرید #{po.id}" + (f" — {po.order_no}" if po.order_no else ""),
                status=po.status,
                relation="purchase_order",
                created_at=po.created_at,
                link_ref_type="purchase_request" if po.request_id else None,
                link_ref_id=po.request_id,
            ),
        )

    for grn in (
        db.query(GoodsReceipt)
        .filter(GoodsReceipt.request_id == request_id)
        .order_by(GoodsReceipt.id.asc())
        .all()
    ):
        inst = _latest_workflow(db, WORKFLOW_REF_GRN, grn.id)
        _add_unique(
            items,
            seen,
            RelatedRequestItem(
                ref_type=WORKFLOW_REF_GRN,
                ref_id=grn.id,
                label="رسید انبار (GRN)",
                title=f"رسید انبار #{grn.id}" + (f" — {grn.grn_no}" if grn.grn_no else ""),
                status=grn.status,
                relation="goods_receipt",
                workflow_instance_id=inst.id if inst else None,
                workflow_status=inst.status if inst else None,
                created_at=grn.created_at,
                link_ref_type="purchase_request",
                link_ref_id=grn.request_id,
            ),
        )


def _collect_payment_request_chain(
    db: Session, payment_id: int, items: list[RelatedRequestItem], seen: set[tuple[str, int, str]]
) -> None:
    pr = db.get(PaymentRequest, payment_id)
    for wf_ref in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
        inst = _latest_workflow(db, wf_ref, payment_id)
        if inst:
            _add_unique(
                items,
                seen,
                _item_from_workflow(
                    inst,
                    relation="workflow",
                    title=f"درخواست مالی #{payment_id}"
                    + (f" — {float(pr.amount):,.0f} ریال" if pr else ""),
                    status=pr.status if pr else None,
                    created_at=pr.created_at if pr else None,
                ),
            )

    req = (
        db.query(Request)
        .filter(
            Request.payment_request_id == payment_id,
            Request.type == REQUEST_TYPE_PURCHASE,
        )
        .first()
    )
    if req:
        _collect_purchase_request_chain(db, req.id, items, seen)


def _collect_simple_workflow_entity(
    db: Session,
    *,
    ref_type: str,
    ref_id: int,
    entity_label: str,
    title: str,
    status: str | None,
    created_at: datetime | None,
    items: list[RelatedRequestItem],
    seen: set[tuple[str, int, str]],
) -> None:
    inst = _latest_workflow(db, ref_type, ref_id)
    if inst:
        _add_unique(
            items,
            seen,
            _item_from_workflow(
                inst,
                relation="workflow",
                title=title,
                status=status,
                created_at=created_at,
            ),
        )
    else:
        _add_unique(
            items,
            seen,
            RelatedRequestItem(
                ref_type=ref_type,
                ref_id=ref_id,
                label=entity_label,
                title=title,
                status=status,
                relation="self",
                created_at=created_at,
            ),
        )


def get_related_requests(
    db: Session,
    *,
    ref_type: str,
    ref_id: int,
) -> RelatedRequestsResult | None:
    ref_type = (ref_type or "").strip()
    if not ref_type or ref_id < 1:
        return None

    items: list[RelatedRequestItem] = []
    seen: set[tuple[str, int, str]] = set()

    if ref_type in PURCHASE_WORKFLOW_REFS or ref_type == "product_request":
        anchor_type = "purchase_request"
        _collect_purchase_request_chain(db, ref_id, items, seen)
        anchor_label = _label(anchor_type)
    elif ref_type in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
        anchor_type = "payment_request"
        _collect_payment_request_chain(db, ref_id, items, seen)
        anchor_label = _label("payment_request")
    elif ref_type == WORKFLOW_REF_GRN:
        grn = db.get(GoodsReceipt, ref_id)
        if not grn:
            return None
        anchor_type = WORKFLOW_REF_GRN
        anchor_label = _label(WORKFLOW_REF_GRN)
        inst = _latest_workflow(db, WORKFLOW_REF_GRN, ref_id)
        if inst:
            _add_unique(
                items,
                seen,
                _item_from_workflow(
                    inst,
                    relation="self",
                    title=f"رسید انبار #{ref_id}",
                    status=grn.status,
                    created_at=grn.created_at,
                ),
            )
        _collect_purchase_request_chain(db, grn.request_id, items, seen)
    elif ref_type == "purchase_order":
        po = db.get(PurchaseOrder, ref_id)
        if not po:
            return None
        anchor_type = "purchase_order"
        anchor_label = "سفارش خرید"
        _add_unique(
            items,
            seen,
            RelatedRequestItem(
                ref_type="purchase_order",
                ref_id=po.id,
                label=anchor_label,
                title=f"سفارش خرید #{po.id}",
                status=po.status,
                relation="self",
                created_at=po.created_at,
            ),
        )
        if po.request_id:
            _collect_purchase_request_chain(db, po.request_id, items, seen)
    elif ref_type == "petty_cash":
        row = db.get(PettyCashRequest, ref_id)
        if not row:
            return None
        anchor_type = ref_type
        anchor_label = _label(ref_type)
        _collect_simple_workflow_entity(
            db,
            ref_type=ref_type,
            ref_id=ref_id,
            entity_label=anchor_label,
            title=f"تنخواه #{ref_id} — {float(row.amount):,.0f} ریال",
            status=row.status,
            created_at=row.created_at,
            items=items,
            seen=seen,
        )
    elif ref_type == "mission_request":
        row = db.get(MissionRequest, ref_id)
        if not row:
            return None
        anchor_type = ref_type
        anchor_label = _label(ref_type)
        _collect_simple_workflow_entity(
            db,
            ref_type=ref_type,
            ref_id=ref_id,
            entity_label=anchor_label,
            title=f"ماموریت #{ref_id} — {row.destination[:40]}",
            status=row.status,
            created_at=row.created_at,
            items=items,
            seen=seen,
        )
    elif ref_type in (WORKFLOW_REF_FINANCIAL_DOCUMENT, "financial_document"):
        row = db.get(FinancialDocument, ref_id)
        if not row:
            return None
        anchor_type = WORKFLOW_REF_FINANCIAL_DOCUMENT
        anchor_label = _label(WORKFLOW_REF_FINANCIAL_DOCUMENT)
        title = row.title or row.description or f"سند مالی #{ref_id}"
        _collect_simple_workflow_entity(
            db,
            ref_type=WORKFLOW_REF_FINANCIAL_DOCUMENT,
            ref_id=ref_id,
            entity_label=anchor_label,
            title=title[:120],
            status=row.status,
            created_at=row.created_at,
            items=items,
            seen=seen,
        )
    else:
        inst = _latest_workflow(db, ref_type, ref_id)
        if not inst:
            return None
        anchor_type = ref_type
        anchor_label = _label(ref_type)
        _add_unique(
            items,
            seen,
            _item_from_workflow(inst, relation="self", title=f"{anchor_label} #{ref_id}"),
        )

    if not items:
        return None

    items.sort(key=lambda x: (x.created_at or datetime.min, x.ref_id))

    return RelatedRequestsResult(
        anchor_ref_type=anchor_type,
        anchor_ref_id=ref_id,
        anchor_label=anchor_label,
        items=items,
    )


def get_related_requests_for_instance(db: Session, instance_id: int) -> RelatedRequestsResult | None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None
    return get_related_requests(db, ref_type=inst.ref_type, ref_id=inst.ref_id)
