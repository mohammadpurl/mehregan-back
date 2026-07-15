"""شروع نمونه گردش‌کار — قابل فراخوانی هم‌زمان از API و هم از consumer."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.infrastructure.messaging.publisher import publish_event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_definition_service import get_steps_config
from app.services.workflow_step_config import (
    SUBMITTER_MANAGER,
    format_missing_role_assignee_error,
    is_ceo_role_step,
    resolve_role_id_for_step,
    resolve_step_assignee_user,
)


def _parse_assignees_by_order(payload: dict) -> dict[int, int]:
    raw = payload.get("assignees_by_order") or {}
    out: dict[int, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
    uid = payload.get("user_id") or payload.get("first_assignee_user_id")
    if uid is not None and 1 not in out:
        try:
            out[1] = int(uid)
        except (TypeError, ValueError):
            pass
    return out


def _existing_active_instance(db: Session, ref_type: str, ref_id: int) -> WorkflowInstance | None:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == ref_type,
            WorkflowInstance.ref_id == ref_id,
            WorkflowInstance.status.in_(("pending", "in_progress", "active")),
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def start_workflow_instance(
    db: Session,
    payload: dict,
    *,
    sync_notify: bool = False,
) -> WorkflowInstance:
    """
    نمونه و مراحل را می‌سازد و workflow.next_step را منتشر می‌کند.
    اگر نمونهٔ فعال از قبل وجود داشته باشد، همان را برمی‌گرداند (idempotent).
    """
    ref_type = payload.get("ref_type")
    ref_id = payload.get("ref_id")
    if not ref_type or not ref_id:
        raise ValueError("workflow.start requires ref_type and ref_id")
    ref_id = int(ref_id)

    existing = _existing_active_instance(db, str(ref_type), ref_id)
    if existing:
        return existing

    submitter_id = payload.get("submitter_id") or payload.get("requester_id")
    if submitter_id is not None:
        try:
            submitter_id = int(submitter_id)
        except (TypeError, ValueError):
            submitter_id = None

    steps_config = get_steps_config(db, str(ref_type))
    assignees = _parse_assignees_by_order(payload)

    instance = WorkflowInstance(
        ref_type=ref_type,
        ref_id=ref_id,
        status="pending",
    )
    db.add(instance)
    db.flush()

    created_steps: list[WorkflowStep] = []
    assigned_user_ids: list[int] = []
    for idx, step_cfg in enumerate(steps_config, start=1):
        role_id = resolve_role_id_for_step(db, step_cfg)
        override = assignees.get(idx)
        # فقط تأییدکنندهٔ مرحلهٔ قبل از انتخاب حذف شود — همان مدیرعامل می‌تواند
        # در مراحل غیرمتوالی (مثلاً ۲ و ۴) دوباره تأیید کند.
        exclude = [assigned_user_ids[-1]] if assigned_user_ids else []
        assignee = resolve_step_assignee_user(
            db,
            step_cfg,
            role_id=role_id,
            submitter_id=submitter_id,
            override_user_id=override,
            exclude_user_ids=exclude,
        )
        if assignee is None and exclude:
            # مدیر مستقیم = تنها مدیرعامل: مرحلهٔ تکراری مدیرعامل را رد کن
            prev_cfg = steps_config[idx - 2] if idx >= 2 else None
            same_person = resolve_step_assignee_user(
                db,
                step_cfg,
                role_id=role_id,
                submitter_id=submitter_id,
                override_user_id=override,
                exclude_user_ids=None,
            )
            if (
                same_person
                and same_person.id == assigned_user_ids[-1]
                and prev_cfg
                and (prev_cfg.get("assignee_strategy") or "") == SUBMITTER_MANAGER
                and is_ceo_role_step(step_cfg)
            ):
                continue
            db.rollback()
            raise ValueError(
                format_missing_role_assignee_error(
                    db, step_cfg, role_id, exclude_user_ids=exclude
                )
            )
        if assignee is None:
            db.rollback()
            raise ValueError(
                format_missing_role_assignee_error(
                    db, step_cfg, role_id, exclude_user_ids=exclude
                )
            )
        if assigned_user_ids and assignee.id == assigned_user_ids[-1]:
            db.rollback()
            raise ValueError(
                f"مرحله {idx} و مرحله قبل به یک کاربر ({assignee.id}) اختصاص یافته‌اند؛ "
                "دو مرحلهٔ پشت‌سرهم نباید به یک نفر برسند (مثلاً مدیر مالی و مدیرعامل)."
            )
        assigned_user_ids.append(assignee.id)
        step = WorkflowStep(
            instance_id=instance.id,
            role_id=role_id,
            order=idx,
            status="pending",
            assigned_user_id=assignee.id,
        )
        db.add(step)
        db.flush()
        created_steps.append(step)

    if not created_steps:
        db.rollback()
        raise ValueError("هیچ مرحلهٔ قابل تخصیص برای گردش‌کار ساخته نشد")

    first_step = created_steps[0]
    db.commit()
    db.refresh(instance)

    next_payload = {
        "instance_id": instance.id,
        "role_id": first_step.role_id,
        "step_id": first_step.id,
        "user_id": first_step.assigned_user_id,
        "ref_type": ref_type,
        "ref_id": ref_id,
    }
    publish_event("workflow.next_step", next_payload)
    if sync_notify:
        from app.services.workflow_notifications import notify_workflow_next_step

        notify_workflow_next_step(db, next_payload)
        db.commit()

    return instance
