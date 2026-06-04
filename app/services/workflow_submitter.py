"""Resolve original submitter for workflow instances."""

from sqlalchemy.orm import Session

from app.models.payment_request import PaymentRequest
from app.models.petty_cash_request import PettyCashRequest
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_form import WorkflowForm
from app.models.warehouse_form import WarehouseForm
from app.models.request import Request


def resolve_submitter_id(db: Session, inst: WorkflowInstance) -> int | None:
    ref_type = (inst.ref_type or "").strip()
    ref_id = inst.ref_id

    if ref_type == "payment_request":
        pr = db.get(PaymentRequest, ref_id)
        return pr.requester_id if pr else None
    if ref_type == "petty_cash":
        pc = db.get(PettyCashRequest, ref_id)
        return pc.requester_id if pc else None
    if ref_type == "workflow_form":
        wf = db.get(WorkflowForm, ref_id)
        return wf.requester_id if wf else None
    if ref_type == "warehouse_form":
        wh = db.get(WarehouseForm, ref_id)
        return wh.requester_id if wh else None
    if ref_type in ("request", "procurement"):
        req = db.get(Request, ref_id)
        return req.requester_id if req else None
    return None
