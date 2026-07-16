from sqlalchemy.orm import Session

from app.constants.petty_cash import WORKFLOW_REF_PETTY_CASH_SETTLEMENT
from app.models.workflow_instance import WorkflowInstance
from app.services.petty_cash import (
    on_settlement_workflow_approved,
    on_settlement_workflow_rejected,
    on_workflow_approved,
    on_workflow_rejected,
)


def handle_workflow_approved(db: Session, payload: dict) -> None:
    instance_id = payload.get("instance_id")
    if not instance_id:
        return
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return
    if inst.ref_type == "petty_cash":
        on_workflow_approved(db, inst.ref_id)
    elif inst.ref_type == WORKFLOW_REF_PETTY_CASH_SETTLEMENT:
        on_settlement_workflow_approved(db, inst.ref_id)


def handle_workflow_rejected(db: Session, payload: dict) -> None:
    instance_id = payload.get("instance_id")
    if not instance_id:
        return
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return
    if inst.ref_type == "petty_cash":
        on_workflow_rejected(db, inst.ref_id)
    elif inst.ref_type == WORKFLOW_REF_PETTY_CASH_SETTLEMENT:
        on_settlement_workflow_rejected(db, inst.ref_id)
