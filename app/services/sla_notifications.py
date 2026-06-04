"""اعلان‌های SLA — گیرنده کار و مدیرعامل."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ad_hoc_task import AdHocTask
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import create_inbox_item
from app.services.notification import create_notification
from app.services.workflow_messages import ref_type_label

CEO_ROLE_ALIASES = ("ceo", "managing_director", "مدیرعامل")


def get_ceo_user_ids(db: Session) -> list[int]:
    """شناسه کاربران فعال با نقش مدیرعامل."""
    roles = (
        db.query(Role)
        .filter(func.lower(Role.name).in_([a.lower() for a in CEO_ROLE_ALIASES]))
        .all()
    )
    role_ids = [r.id for r in roles]
    if not role_ids:
        return []

    rows = (
        db.query(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(
            UserRole.role_id.in_(role_ids),
            UserRole.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows]


def _notify_user(
    db: Session,
    *,
    user_id: int,
    title: str,
    message: str,
    notif_type: str,
    ref_id: int,
    ref_type: str,
    role_id: int | None = None,
) -> None:
    create_inbox_item(
        db,
        role_id=role_id,
        title=title,
        message=message,
        ref_id=ref_id,
        ref_type=ref_type,
        preferred_user_id=user_id,
    )
    create_notification(
        db,
        user_id,
        title=title,
        message=message,
        type=notif_type,
        ref_id=ref_id,
        ref_type=ref_type,
    )


def notify_workflow_sla_breach(
    db: Session,
    *,
    instance: WorkflowInstance,
    step: WorkflowStep,
) -> None:
    """اعلان تأخیر SLA گردش‌کار به گیرنده و مدیرعامل."""
    label = ref_type_label(instance.ref_type)
    title = f"تأخیر SLA — {label}"
    message = (
        f"مهلت انجام مرحله {step.order} برای {label} به پایان رسیده است. "
        "لطفاً در اسرع وقت اقدام کنید."
    )

    notified: set[int] = set()

    if step.assigned_user_id:
        uid = int(step.assigned_user_id)
        _notify_user(
            db,
            user_id=uid,
            title=title,
            message=message,
            notif_type="sla.breached",
            ref_id=instance.id,
            ref_type="workflow",
            role_id=step.role_id,
        )
        notified.add(uid)

    for ceo_id in get_ceo_user_ids(db):
        if ceo_id in notified:
            continue
        _notify_user(
            db,
            user_id=ceo_id,
            title=f"گزارش تأخیر SLA — {label}",
            message=(
                f"مرحله {step.order} از {label} توسط گیرنده در مهلت مقرر انجام نشده است."
            ),
            notif_type="sla.escalated",
            ref_id=instance.id,
            ref_type="workflow",
        )
        notified.add(ceo_id)


def notify_ad_hoc_task_sla_breach(db: Session, task: AdHocTask) -> None:
    """اعلان تأخیر کار پیش‌بینی‌نشده به گیرنده و مدیرعامل."""
    title = f"تأخیر انجام کار: {task.title}"
    assignee_message = (
        f"مهلت انجام کار «{task.title}» به پایان رسیده است. "
        "لطفاً در اسرع وقت اقدام کنید."
    )
    ceo_message = (
        f"کار پیش‌بینی‌نشده «{task.title}» توسط گیرنده فعلی "
        "در مهلت مقرر انجام نشده است."
    )

    notified: set[int] = set()

    if task.current_assignee_id:
        uid = int(task.current_assignee_id)
        _notify_user(
            db,
            user_id=uid,
            title=title,
            message=assignee_message,
            notif_type="ad_hoc_task.sla_breached",
            ref_id=task.id,
            ref_type="ad_hoc_task",
        )
        notified.add(uid)

    for ceo_id in get_ceo_user_ids(db):
        if ceo_id in notified:
            continue
        _notify_user(
            db,
            user_id=ceo_id,
            title=f"گزارش تأخیر — {task.title}",
            message=ceo_message,
            notif_type="ad_hoc_task.sla_escalated",
            ref_id=task.id,
            ref_type="ad_hoc_task",
        )
        notified.add(ceo_id)
