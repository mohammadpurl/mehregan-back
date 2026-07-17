"""لغو workflow و پاک‌سازی inbox/notification هنگام حذف درخواست."""

from __future__ import annotations

from collections.abc import Sequence

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
    """همه نمونه‌های workflow این ref را لغو و نوتیفیکیشن/کارتابل را پاک می‌کند."""
    instances = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == ref_id,
        )
        .order_by(WorkflowInstance.id.asc())
        .all()
    )
    for inst in instances:
        cancel_workflow_instance(db, inst.id)


def cancel_workflows_for_refs(
    db: Session, ref_types: Sequence[str], ref_id: int
) -> None:
    for ref_type in ref_types:
        cancel_workflow_for_ref(db, ref_type, ref_id)


def workflow_has_approved_step_for_refs(
    db: Session, *, ref_types: Sequence[str], ref_id: int
) -> bool:
    """اگر برای هر یک از ref_typeها حداقل یک مرحلهٔ approved وجود داشته باشد."""
    types = [t for t in ref_types if t]
    if not types or ref_id < 1:
        return False
    instance_ids = [
        row.id
        for row in db.query(WorkflowInstance.id)
        .filter(
            WorkflowInstance.ref_type.in_(types),
            WorkflowInstance.ref_id == ref_id,
        )
        .all()
    ]
    if not instance_ids:
        return False
    return (
        db.query(WorkflowStep.id)
        .filter(
            WorkflowStep.instance_id.in_(instance_ids),
            WorkflowStep.status == "approved",
        )
        .first()
        is not None
    )


def ensure_request_deletable(
    db: Session, *, ref_types: str | Sequence[str], ref_id: int
) -> None:
    """
    حذف فقط قبل از اولین تأیید مجاز است.
    پس از تأیید حتی یک مرحله، حذف ممنوع است (بدون استثنای اصلاح‌کننده).
    """
    types: tuple[str, ...]
    if isinstance(ref_types, str):
        types = (ref_types,)
    else:
        types = tuple(ref_types)
    if workflow_has_approved_step_for_refs(db, ref_types=types, ref_id=ref_id):
        raise ValueError(
            "این درخواست پس از حداقل یک مرحله تأیید قابل حذف نیست. "
            "فقط قبل از اولین تأیید می‌توان آن را حذف کرد."
        )
