"""قفل ویرایش درخواست پس از شروع گردش‌کار / اولین تأیید."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep


def active_workflow_instance(
    db: Session, *, ref_type: str, ref_id: int
) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == ref_id,
            WorkflowInstance.status.in_(("pending", "in_progress", "active", "returned")),
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def workflow_has_approved_step_for_ref(db: Session, *, ref_type: str, ref_id: int) -> bool:
    inst = active_workflow_instance(db, ref_type=ref_type, ref_id=ref_id)
    if not inst:
        inst = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.ref_type == ref_type,
                WorkflowInstance.ref_id == ref_id,
            )
            .order_by(WorkflowInstance.id.desc())
            .first()
        )
    if not inst:
        return False
    return (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.instance_id == inst.id,
            WorkflowStep.status == "approved",
        )
        .count()
        > 0
    )


def user_may_bypass_workflow_edit_lock(user) -> bool:
    if user is None:
        return False
    if getattr(user, "has_permission", None) and user.has_permission("workflow.correction"):
        return True
    if getattr(user, "has_permission", None) and user.has_permission("admin.manage"):
        return True
    return user.has_role("workflow_corrector") if hasattr(user, "has_role") else False


def ensure_workflow_mutable_for_entity(
    db: Session,
    *,
    ref_type: str,
    ref_id: int,
    user,
) -> None:
    """پس از اولین تأیید، فقط نقش اصلاح‌کننده گردش‌کار می‌تواند درخواست را ویرایش کند."""
    if user_may_bypass_workflow_edit_lock(user):
        return
    if workflow_has_approved_step_for_ref(db, ref_type=ref_type, ref_id=ref_id):
        raise ValueError(
            "این درخواست پس از شروع تأیید قفل شده است. "
            "فقط کاربر با نقش «اصلاح‌کننده گردش‌کار» می‌تواند آن را ویرایش کند."
        )
