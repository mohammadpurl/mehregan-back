"""Inbox/notification side-effects for workflow events (used by consumer)."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.inbox import (
    create_inbox_item,
    find_open_workflow_inbox,
    mark_inbox_done_for_workflow,
)
from app.services.notification import create_notification
from app.services.notification_dispatcher import dispatch_notification
from app.services.workflow_messages import (
    inbox_message_for_step,
    inbox_title_for_step,
    notification_message_for_step,
    notification_message_rejected,
    notification_title_for_step,
    notification_title_rejected,
    ref_type_label,
)
from app.services.workflow_feed_context import build_workflow_notify_context
from app.services.workflow_submitter import resolve_submitter_id

logger = logging.getLogger(__name__)


def notify_workflow_next_step(db: Session, payload: dict) -> int | None:
    """
    کارتابل و اعلان مرحله بعد گردش‌کار — هم‌زمان با API (بدون وابستگی به consumer).
    """
    user_id = payload.get("user_id")
    role_id = payload.get("role_id")
    instance_id = payload.get("instance_id")
    step_id = payload.get("step_id")

    if step_id:
        st = db.get(WorkflowStep, step_id)
        if st and st.assigned_user_id:
            user_id = st.assigned_user_id

    if not role_id or not instance_id:
        logger.warning("notify_workflow_next_step skipped: missing role_id/instance_id %s", payload)
        return None

    inst = db.get(WorkflowInstance, instance_id)
    ref_type = inst.ref_type if inst else None
    step_order = None
    if step_id:
        st = db.get(WorkflowStep, step_id)
        if st:
            step_order = st.order

    ctx = build_workflow_notify_context(db, inst, step_order=step_order)
    title = inbox_title_for_step(ref_type, step_order, ctx=ctx)
    message = inbox_message_for_step(ref_type, step_order, ctx=ctx)

    target_user_id = user_id
    if target_user_id:
        existing = find_open_workflow_inbox(
            db, instance_id=instance_id, user_id=int(target_user_id)
        )
        if not existing:
            create_inbox_item(
                db=db,
                role_id=role_id,
                title=title,
                message=message,
                ref_id=instance_id,
                ref_type="workflow",
                preferred_user_id=int(target_user_id),
            )
    else:
        inbox_item = create_inbox_item(
            db=db,
            role_id=role_id,
            title=title,
            message=message,
            ref_id=instance_id,
            ref_type="workflow",
            preferred_user_id=None,
        )
        target_user_id = inbox_item.user_id

    if not target_user_id:
        return None

    if step_id and instance_id:
        st = db.get(WorkflowStep, step_id)
        inst = db.get(WorkflowInstance, instance_id)
        if st and inst:
            from app.services.sla import create_sla_for_workflow_step

            create_sla_for_workflow_step(db, step=st, instance=inst)

    notif = create_notification(
        db=db,
        user_id=int(target_user_id),
        title=notification_title_for_step(ref_type, ctx=ctx),
        message=notification_message_for_step(ref_type, step_order, ctx=ctx),
        type="workflow",
        ref_id=instance_id,
        ref_type="workflow",
        dedupe_unread=True,
    )
    try:
        asyncio.run(
            dispatch_notification(
                int(target_user_id),
                {
                    "type": "workflow.next_step",
                    "instance_id": instance_id,
                    "step_id": step_id,
                    "title": title,
                    "message": notification_message_for_step(
                        ref_type, step_order, ctx=ctx
                    ),
                    "ref_type": ref_type,
                    "ref_label": ref_type_label(ref_type),
                },
            )
        )
    except Exception:
        logger.exception("WebSocket dispatch failed for notification %s", notif.id)

    return int(target_user_id)


def notify_workflow_rejected(
    db: Session,
    *,
    instance_id: int,
    rejected_by_user_id: int | None = None,
    comment: str | None = None,
) -> int | None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None

    mark_inbox_done_for_workflow(db, instance_id)

    submitter_id = resolve_submitter_id(db, inst)
    if not submitter_id:
        return None

    ctx = build_workflow_notify_context(db, inst)
    label = ctx.display_label if ctx else ref_type_label(inst.ref_type)
    title = notification_title_rejected(label)
    message = notification_message_rejected(label, comment=comment)

    create_notification(
        db=db,
        user_id=submitter_id,
        title=title,
        message=message,
        type="workflow.rejected",
        ref_id=instance_id,
        ref_type="workflow",
    )

    create_inbox_item(
        db=db,
        role_id=None,
        title=title,
        message=message,
        ref_id=instance_id,
        ref_type="workflow",
        preferred_user_id=submitter_id,
    )
    return submitter_id


def notify_sla_escalation(
    db: Session,
    *,
    instance_id: int,
    step_id: int,
    role_id: int,
    target_user_id: int | None,
    escalate_to_role_id: int | None = None,
) -> int | None:
    from app.services.sla_notifications import notify_workflow_sla_breach

    inst = db.get(WorkflowInstance, instance_id)
    step = db.get(WorkflowStep, step_id)
    if not inst or not step:
        return None

    notify_workflow_sla_breach(db, instance=inst, step=step)
    return target_user_id or step.assigned_user_id
