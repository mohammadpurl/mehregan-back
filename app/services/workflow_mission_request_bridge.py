from sqlalchemy.orm import Session

from app.constants.mission_request import REF_TYPE, WORKFLOW_REF_MISSION_REPORT
from app.models.workflow_instance import WorkflowInstance
from app.services.mission_request import (
    on_report_workflow_approved,
    on_report_workflow_rejected,
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
    if inst.ref_type == REF_TYPE:
        on_workflow_approved(db, inst.ref_id)
    elif inst.ref_type == WORKFLOW_REF_MISSION_REPORT:
        on_report_workflow_approved(db, inst.ref_id)


def handle_workflow_rejected(db: Session, payload: dict) -> None:
    instance_id = payload.get("instance_id")
    if not instance_id:
        return
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return
    if inst.ref_type == REF_TYPE:
        on_workflow_rejected(db, inst.ref_id)
    elif inst.ref_type == WORKFLOW_REF_MISSION_REPORT:
        on_report_workflow_rejected(db, inst.ref_id)
