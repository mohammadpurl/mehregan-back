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
from app.models.user import User
from app.services.workflow_messages import (
    inbox_message_for_step,
    inbox_title_for_step,
    notification_message_for_step,
    notification_message_step_approved,
    notification_message_step_rejected,
    notification_title_for_step,
    notification_title_step_approved,
    notification_title_step_rejected,
    ref_type_label,
)
from app.services.workflow_feed_context import build_workflow_notify_context
from app.services.workflow_submitter import resolve_submitter_id

logger = logging.getLogger(__name__)


def _actor_display_name(user: User | None) -> str | None:
    if not user:
        return None
    name = getattr(user, "full_name", None)
    if name and str(name).strip():
        return str(name).strip()
    return None


def _dispatch_ws(user_id: int, payload: dict, *, notif_id: int | None = None) -> None:
    try:
        asyncio.run(dispatch_notification(int(user_id), payload))
    except Exception:
        logger.exception(
            "WebSocket dispatch failed for notification %s", notif_id
        )


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
    _dispatch_ws(
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
        notif_id=notif.id,
    )

    return int(target_user_id)


def notify_submitter_step_decision(
    db: Session,
    *,
    instance_id: int,
    decision: str,
    step_order: int | None = None,
    actor: User | None = None,
    comment: str | None = None,
    final: bool = False,
    returned_to_previous: bool = False,
    create_inbox: bool = False,
) -> int | None:
    """اعلان وضعیت تأیید/رد هر مرحله برای درخواست‌دهنده."""
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None

    submitter_id = resolve_submitter_id(db, inst)
    if not submitter_id:
        logger.warning(
            "notify_submitter_step_decision: no submitter for instance=%s ref=%s/%s",
            instance_id,
            inst.ref_type,
            inst.ref_id,
        )
        return None

    if actor is not None and int(submitter_id) == int(actor.id):
        return None

    ctx = build_workflow_notify_context(db, inst, step_order=step_order)
    label = ctx.display_label if ctx else ref_type_label(inst.ref_type)
    actor_name = _actor_display_name(actor)
    decision_norm = (decision or "").strip().lower()

    if decision_norm == "approved":
        title = notification_title_step_approved(label, step_order=step_order)
        message = notification_message_step_approved(
            label,
            step_order=step_order,
            actor_name=actor_name,
            final=final,
        )
        notif_type = "workflow.step_approved" if not final else "workflow.approved"
        ws_type = "workflow.step_approved" if not final else "workflow.approved"
    else:
        title = notification_title_step_rejected(
            label,
            step_order=step_order,
            returned_to_previous=returned_to_previous,
        )
        message = notification_message_step_rejected(
            label,
            step_order=step_order,
            actor_name=actor_name,
            comment=comment,
            returned_to_previous=returned_to_previous,
        )
        notif_type = "workflow.rejected"
        ws_type = "workflow.rejected"

    notif = create_notification(
        db=db,
        user_id=submitter_id,
        title=title,
        message=message,
        type=notif_type,
        ref_id=instance_id,
        ref_type="workflow",
        dedupe_unread=False,
    )

    if create_inbox:
        create_inbox_item(
            db=db,
            role_id=None,
            title=title,
            message=message,
            ref_id=instance_id,
            ref_type="workflow",
            preferred_user_id=submitter_id,
        )

    _dispatch_ws(
        int(submitter_id),
        {
            "type": ws_type,
            "instance_id": instance_id,
            "step_order": step_order,
            "title": title,
            "message": message,
            "ref_type": inst.ref_type,
            "ref_label": label,
            "final": final,
            "returned_to_previous": returned_to_previous,
        },
        notif_id=notif.id if notif else None,
    )
    return submitter_id


def notify_workflow_rejected(
    db: Session,
    *,
    instance_id: int,
    rejected_by_user_id: int | None = None,
    comment: str | None = None,
    step_order: int | None = None,
    actor: User | None = None,
) -> int | None:
    """رد کامل و بازگشت به درخواست‌کننده — اعلان + کارتابل."""
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None

    mark_inbox_done_for_workflow(db, instance_id)

    if actor is None and rejected_by_user_id:
        actor = db.get(User, rejected_by_user_id)

    return notify_submitter_step_decision(
        db,
        instance_id=instance_id,
        decision="rejected",
        step_order=step_order,
        actor=actor,
        comment=comment,
        returned_to_previous=False,
        create_inbox=True,
    )


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
