from sqlalchemy.orm import Session

from app.models.workflow_instance import WorkflowInstance
from app.services.petty_cash import on_workflow_approved, on_workflow_rejected


def handle_workflow_approved(db: Session, payload: dict) -> None:
    instance_id = payload.get("instance_id")
    if not instance_id:
        return
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type != "petty_cash":
        return
    on_workflow_approved(db, inst.ref_id)


def handle_workflow_rejected(db: Session, payload: dict) -> None:
    instance_id = payload.get("instance_id")
    if not instance_id:
        return
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type != "petty_cash":
        return
    on_workflow_rejected(db, inst.ref_id)
