"""گزارش SLA برای مدیرعامل — زمان انجام کارها توسط اشخاص."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from sqlalchemy.orm import Session

from app.models.ad_hoc_task import STATUS_CLOSED, AdHocTask
from app.models.sla_record import SLARecord
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_messages import ref_type_label

SlaItemStatus = Literal["on_time", "late", "overdue", "in_progress", "unknown"]

STATUS_LABELS: dict[str, str] = {
    "on_time": "به‌موقع",
    "late": "با تأخیر",
    "overdue": "معوق",
    "in_progress": "در جریان",
    "unknown": "نامشخص",
}


def _user_display(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def _period_bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(date_from, time.min) if date_from else None
    end = datetime.combine(date_to, time.max) if date_to else None
    return start, end


def _minutes_between(start: datetime | None, end: datetime | None) -> int | None:
    if not start or not end:
        return None
    delta = end - start
    return max(0, int(delta.total_seconds() // 60))


def _resolve_sla_status(
    *,
    due_at: datetime | None,
    completed_at: datetime | None,
    is_pending: bool,
    now: datetime,
) -> SlaItemStatus:
    if is_pending:
        if due_at and due_at < now:
            return "overdue"
        return "in_progress"
    if not completed_at:
        return "unknown"
    if not due_at:
        return "unknown"
    return "on_time" if completed_at <= due_at else "late"


def _in_period(
    *,
    start: datetime | None,
    end: datetime | None,
    event_at: datetime | None,
) -> bool:
    if event_at is None:
        return start is None and end is None
    if start and event_at < start:
        return False
    if end and event_at > end:
        return False
    return True


def _build_summary(items: list[dict]) -> dict:
    on_time = sum(1 for i in items if i["status"] == "on_time")
    late = sum(1 for i in items if i["status"] == "late")
    overdue = sum(1 for i in items if i["status"] == "overdue")
    in_progress = sum(1 for i in items if i["status"] == "in_progress")
    completed = on_time + late
    compliance = round((on_time / completed) * 100, 2) if completed else 0.0

    by_user: dict[int, dict] = {}
    for item in items:
        uid = item.get("assignee_id")
        if not uid:
            continue
        bucket = by_user.setdefault(
            uid,
            {
                "user_id": uid,
                "assignee_name": item.get("assignee_name"),
                "total": 0,
                "on_time": 0,
                "late": 0,
                "overdue": 0,
                "in_progress": 0,
                "duration_minutes_total": 0,
                "duration_samples": 0,
            },
        )
        bucket["total"] += 1
        st = item["status"]
        if st in bucket:
            bucket[st] += 1
        dur = item.get("duration_minutes")
        if dur is not None:
            bucket["duration_minutes_total"] += dur
            bucket["duration_samples"] += 1

    by_assignee: list[dict] = []
    for row in by_user.values():
        samples = row.pop("duration_samples")
        total_dur = row.pop("duration_minutes_total")
        row["avg_duration_minutes"] = (
            round(total_dur / samples) if samples else None
        )
        completed_user = row["on_time"] + row["late"]
        row["compliance_rate_percent"] = (
            round((row["on_time"] / completed_user) * 100, 2)
            if completed_user
            else None
        )
        by_assignee.append(row)

    by_assignee.sort(key=lambda r: (-r["total"], r["assignee_name"] or ""))

    return {
        "total": len(items),
        "on_time": on_time,
        "late": late,
        "overdue_pending": overdue,
        "in_progress": in_progress,
        "compliance_rate_percent": compliance,
        "by_assignee": by_assignee,
    }


def _workflow_items(
    db: Session,
    *,
    period_start: datetime | None,
    period_end: datetime | None,
    ref_type: str | None,
    assignee_id: int | None,
    now: datetime,
) -> list[dict]:
    query = (
        db.query(WorkflowStep, WorkflowInstance, SLARecord)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowStep.instance_id)
        .outerjoin(SLARecord, SLARecord.step_id == WorkflowStep.id)
        .filter(WorkflowStep.assigned_user_id.isnot(None))
    )
    if ref_type:
        query = query.filter(WorkflowInstance.ref_type == ref_type)
    if assignee_id:
        query = query.filter(WorkflowStep.assigned_user_id == assignee_id)

    rows = query.order_by(WorkflowStep.approved_at.desc().nullslast(), WorkflowStep.id.desc()).all()
    items: list[dict] = []

    for step, inst, sla in rows:
        is_pending = step.status == "pending"
        completed_at = step.approved_at if not is_pending else None
        due_at = sla.due_at if sla else None
        started_at = sla.created_at if sla else None

        event_at = completed_at or due_at or started_at
        if not _in_period(start=period_start, end=period_end, event_at=event_at):
            if not (is_pending and due_at and due_at < now):
                continue

        assignee = db.get(User, step.assigned_user_id) if step.assigned_user_id else None
        status = _resolve_sla_status(
            due_at=due_at,
            completed_at=completed_at,
            is_pending=is_pending,
            now=now,
        )
        duration = _minutes_between(started_at, completed_at)

        items.append(
            {
                "kind": "workflow",
                "ref_type": inst.ref_type,
                "ref_label": ref_type_label(inst.ref_type),
                "instance_id": inst.id,
                "business_ref_id": inst.ref_id,
                "step_id": step.id,
                "step_order": step.order,
                "step_status": step.status,
                "title": f"{ref_type_label(inst.ref_type)} #{inst.ref_id} — مرحله {step.order}",
                "assignee_id": step.assigned_user_id,
                "assignee_name": _user_display(assignee),
                "started_at": started_at,
                "due_at": due_at,
                "completed_at": completed_at,
                "duration_minutes": duration,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "breached": status in ("late", "overdue"),
            }
        )

    return items


def _ad_hoc_items(
    db: Session,
    *,
    period_start: datetime | None,
    period_end: datetime | None,
    assignee_id: int | None,
    now: datetime,
) -> list[dict]:
    query = db.query(AdHocTask)
    rows = query.order_by(AdHocTask.updated_at.desc()).all()
    items: list[dict] = []

    for task in rows:
        steps = sorted(task.steps, key=lambda s: s.id)
        if not steps:
            continue

        for idx, step in enumerate(steps):
            if not step.assignee_id:
                continue
            if assignee_id and step.assignee_id != assignee_id:
                continue

            started_at = step.created_at
            is_last = idx == len(steps) - 1
            if is_last and task.status == STATUS_CLOSED:
                completed_at = step.created_at
            elif idx + 1 < len(steps):
                completed_at = steps[idx + 1].created_at
            else:
                completed_at = None

            is_current_open = task.status != STATUS_CLOSED and is_last
            due_at = task.due_at if is_current_open else None

            event_at = completed_at or due_at or started_at
            if not _in_period(start=period_start, end=period_end, event_at=event_at):
                if not (is_current_open and due_at and due_at < now):
                    continue

            assignee = db.get(User, step.assignee_id)
            status = _resolve_sla_status(
                due_at=due_at,
                completed_at=completed_at,
                is_pending=is_current_open,
                now=now,
            )
            duration = _minutes_between(started_at, completed_at)

            items.append(
                {
                    "kind": "ad_hoc",
                    "ref_type": "ad_hoc_task",
                    "ref_label": "کار پیش‌بینی‌نشده",
                    "task_id": task.id,
                    "business_ref_id": task.id,
                    "step_id": step.id,
                    "step_order": idx + 1,
                    "step_status": "closed" if completed_at else "open",
                    "title": f"{task.title} — ارجاع {idx + 1}",
                    "assignee_id": step.assignee_id,
                    "assignee_name": _user_display(assignee),
                    "started_at": started_at,
                    "due_at": due_at,
                    "completed_at": completed_at,
                    "duration_minutes": duration,
                    "status": status,
                    "status_label": STATUS_LABELS[status],
                    "breached": status in ("late", "overdue"),
                }
            )

    return items


def get_sla_report(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    ref_type: str | None = None,
    assignee_id: int | None = None,
    kind: str | None = "all",
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """
    گزارش SLA برای مدیرعامل:
    - زمان شروع، مهلت، زمان انجام
    - وضعیت به‌موقع / تأخیر / معوق
    - تجمیع عملکرد هر فرد
    """
    period_start, period_end = _period_bounds(date_from, date_to)
    now = datetime.utcnow()
    kind_norm = (kind or "all").strip().lower()

    items: list[dict] = []
    if kind_norm in ("all", "workflow"):
        items.extend(
            _workflow_items(
                db,
                period_start=period_start,
                period_end=period_end,
                ref_type=ref_type,
                assignee_id=assignee_id,
                now=now,
            )
        )
    if kind_norm in ("all", "ad_hoc") and not ref_type:
        items.extend(
            _ad_hoc_items(
                db,
                period_start=period_start,
                period_end=period_end,
                assignee_id=assignee_id,
                now=now,
            )
        )

    items.sort(
        key=lambda i: (
            i.get("completed_at") or i.get("due_at") or i.get("started_at") or datetime.min
        ),
        reverse=True,
    )

    summary = _build_summary(items)
    total = len(items)
    page_items = items[offset : offset + limit]

    return {
        "period": {
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
        },
        "filters": {
            "ref_type": ref_type,
            "assignee_id": assignee_id,
            "kind": kind_norm,
        },
        "summary": summary,
        "items": page_items,
        "pagination": {
            "total": total,
            "page": (offset // limit) + 1 if limit else 1,
            "pageSize": limit,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
        },
        "generated_at": now.isoformat(),
    }
