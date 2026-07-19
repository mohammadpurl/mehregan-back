"""شروع نمونه گردش‌کار — قابل فراخوانی هم‌زمان از API و هم از consumer."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.infrastructure.messaging.publisher import publish_event
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_definition_service import get_steps_config
from app.services.workflow_step_config import (
    format_missing_role_assignee_error,
    resolve_role_id_for_step,
    resolve_step_assignee_user,
    should_skip_missing_manager_step,
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

    قوانین تخصیص:
    - اگر مرحله submitter_manager باشد و manager_id نباشد → آن مرحله رد می‌شود.
    - یک نفر می‌تواند چند مرحلهٔ پشت‌سرهم داشته باشد؛ با اولین تأیید،
      مراحل بعدیِ همان نفر auto-skip می‌شوند مگر اینکه بین مراحل نیاز به
      ورود/تغییر داده (شرایط مالی یا اقدام عملیاتی) باشد.
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
    for idx, step_cfg in enumerate(steps_config, start=1):
        if should_skip_missing_manager_step(
            db, step_cfg, submitter_id=submitter_id
        ):
            continue

        role_id = resolve_role_id_for_step(db, step_cfg)
        override = assignees.get(idx)
        # عمداً تأییدکنندهٔ قبل را exclude نمی‌کنیم تا همان نفر بتواند
        # مرحلهٔ مدیر مستقیم و مدیرعامل/مالی را با یک تأیید انجام دهد (auto-skip).
        assignee = resolve_step_assignee_user(
            db,
            step_cfg,
            role_id=role_id,
            submitter_id=submitter_id,
            override_user_id=override,
            exclude_user_ids=None,
        )
        if assignee is None:
            db.rollback()
            raise ValueError(
                format_missing_role_assignee_error(
                    db,
                    step_cfg,
                    role_id,
                    exclude_user_ids=None,
                    submitter_id=submitter_id,
                )
            )
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
        raise ValueError(
            "هیچ مرحلهٔ قابل تخصیص برای گردش‌کار ساخته نشد. "
            "تعریف workflow و نقش/مدیر مستقیم کاربران را بررسی کنید."
        )

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
