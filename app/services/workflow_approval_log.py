from sqlalchemy.orm import Session

from app.models.workflow_approval import WorkflowApproval
from app.services.audit import create_audit_log


def record_workflow_decision(
    db: Session,
    *,
    instance_id: int,
    step_id: int,
    approved_by: int,
    decision: str,
    comment: str | None = None,
) -> WorkflowApproval:
    row = WorkflowApproval(
        instance_id=instance_id,
        step_id=step_id,
        approved_by=approved_by,
        decision=decision,
        comment=(comment or "").strip() or None,
    )
    db.add(row)
    db.flush()
    create_audit_log(
        db,
        action=f"workflow.{decision}",
        user_id=approved_by,
        entity="workflow_instance",
        entity_id=instance_id,
        new_data={
            "step_id": step_id,
            "decision": decision,
            "comment": (comment or "").strip() or None,
        },
    )
    return row
