"""Resolve original submitter for workflow instances."""

from sqlalchemy.orm import Session

from app.models.financial_document import FinancialDocument
from app.models.mission_request import MissionRequest
from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.request import Request
from app.models.warehouse_form import WarehouseForm
from app.models.workflow_form import WorkflowForm
from app.models.workflow_instance import WorkflowInstance


def resolve_submitter_id(db: Session, inst: WorkflowInstance) -> int | None:
    """شناسه درخواست‌کنندهٔ اصلی برای هر نوع گردش‌کار."""
    ref_type = (inst.ref_type or "").strip()
    ref_id = inst.ref_id
    if not ref_type or not ref_id:
        return None

    if ref_type in ("payment_request", "payment_order"):
        pr = db.get(PaymentRequest, ref_id)
        return pr.requester_id if pr else None

    if ref_type in ("petty_cash", "petty_cash_settlement"):
        pc = db.get(PettyCashRequest, ref_id)
        return pc.requester_id if pc else None

    if ref_type in ("mission_request", "mission_report"):
        mr = db.get(MissionRequest, ref_id)
        return mr.requester_id if mr else None

    if ref_type == "financial_document":
        fd = db.get(FinancialDocument, ref_id)
        return fd.requester_id if fd else None

    if ref_type == "workflow_form":
        wf = db.get(WorkflowForm, ref_id)
        return wf.requester_id if wf else None

    if ref_type == "warehouse_form":
        wh = db.get(WarehouseForm, ref_id)
        return wh.requester_id if wh else None

    if ref_type in (
        "request",
        "procurement",
        "purchase_request",
        "procurement_proforma",
    ):
        req = db.get(Request, ref_id)
        return req.requester_id if req else None

    return None
