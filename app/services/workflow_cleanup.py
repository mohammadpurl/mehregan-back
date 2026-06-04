"""لغو workflow و پاک‌سازی inbox/notification هنگام حذف درخواست."""

from sqlalchemy.orm import Session

from app.models.inbox import InboxItem
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.notification import delete_notifications_for_workflow


def cancel_workflow_instance(db: Session, instance_id: int) -> None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return

    (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.instance_id == instance_id,
            WorkflowStep.status == "pending",
        )
        .update({"status": "cancelled"}, synchronize_session=False)
    )

    inst.status = "cancelled"

    delete_notifications_for_workflow(db, instance_id)

    db.query(InboxItem).filter(
        InboxItem.ref_type == "workflow",
        InboxItem.ref_id == instance_id,
    ).delete(synchronize_session=False)

    db.flush()


def cancel_workflow_for_ref(db: Session, ref_type: str, ref_id: int) -> None:
    inst = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == ref_id,
        )
        .first()
    )
    if inst:
        cancel_workflow_instance(db, inst.id)
