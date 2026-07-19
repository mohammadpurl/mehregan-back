from typing import Any

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
    field_changes: list[dict[str, Any]] | None = None,
) -> WorkflowApproval:
    changes = list(field_changes) if field_changes else None
    row = WorkflowApproval(
        instance_id=instance_id,
        step_id=step_id,
        approved_by=approved_by,
        decision=decision,
        comment=(comment or "").strip() or None,
        field_changes=changes,
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
            "field_changes": changes,
        },
    )
    if changes:
        create_audit_log(
            db,
            action="workflow.terms_changed",
            user_id=approved_by,
            entity="workflow_instance",
            entity_id=instance_id,
            new_data={
                "step_id": step_id,
                "changes": changes,
            },
        )
    return row
