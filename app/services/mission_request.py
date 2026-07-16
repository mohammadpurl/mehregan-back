from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.mission_request import (
    REF_TYPE,
    STATUS_APPROVED,
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_REPORT_PENDING_APPROVAL,
    WORKFLOW_REF_MISSION_REPORT,
)
from app.infrastructure.messaging.publisher import publish_event
from app.models.mission_request import MissionRequest
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.services.attachment_service import (
    ENTITY_MISSION_REQUEST,
    count_attachments_batch,
    delete_all_for_entity,
    list_attachments,
    serialize_attachment,
)
from app.services.mission_request_list_scope import (
    apply_mission_request_list_scope,
    list_mission_request_available_scopes,
    user_can_access_mission_request_extended,
)
from app.services.payment_request_list_scope import assert_scope_allowed
from app.services.query_utils import apply_search_filter, apply_sort
from app.services.workflow_cleanup import cancel_workflow_for_ref
from app.services.workflow_definition_service import assert_workflow_assignees_ready
from app.services.workflow_start import start_workflow_instance
from app.services.workflow_step_access import user_can_act_on_workflow_step


def workflow_instance_for_mission(
    db: Session, mission_id: int
) -> WorkflowInstance | None:
    """آخرین نمونهٔ فعال تأیید گزارش را ترجیح می‌دهد؛ وگرنه درخواست ماموریت."""
    report = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type == WORKFLOW_REF_MISSION_REPORT,
            WorkflowInstance.ref_id == mission_id,
            WorkflowInstance.status.in_(("in_progress", "pending", "returned")),
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )
    if report:
        return report
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type.in_((REF_TYPE, WORKFLOW_REF_MISSION_REPORT)),
            WorkflowInstance.ref_id == mission_id,
        )
        .order_by(WorkflowInstance.id.desc())
        .first()
    )


def _workflow_instances_for_mission(
    db: Session, mission_id: int
) -> list[WorkflowInstance]:
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.ref_type.in_((REF_TYPE, WORKFLOW_REF_MISSION_REPORT)),
            WorkflowInstance.ref_id == mission_id,
        )
        .all()
    )


def _user_display(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    return " ".join(p.strip() for p in parts if p and p.strip()) or user.username


def _serialize(
    db: Session,
    row: MissionRequest,
    *,
    include_attachments: bool = True,
    attachment_count_override: int | None = None,
) -> dict:
    inst = workflow_instance_for_mission(db, row.id)
    requester_name = None
    if row.requester_id:
        req = db.get(User, row.requester_id)
        requester_name = _user_display(req)

    base = {
        "id": row.id,
        "requester_id": row.requester_id,
        "requester_name": requester_name,
        "destination": row.destination,
        "reason": row.reason,
        "vehicle": row.vehicle,
        "status": row.status,
        "report_text": row.report_text,
        "reported_at": row.reported_at,
        "workflow_instance_id": inst.id if inst else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_attachments:
        atts = list_attachments(db, ENTITY_MISSION_REQUEST, row.id)
        base["attachments"] = [serialize_attachment(a) for a in atts]
        base["attachment_count"] = len(atts)
    else:
        base["attachments"] = []
        base["attachment_count"] = (
            attachment_count_override if attachment_count_override is not None else 0
        )
    return base


def create_mission_request(
    db: Session,
    requester_id: int,
    *,
    destination: str,
    reason: str,
    vehicle: str,
    assignees_by_order: dict[str, int] | None = None,
) -> dict:
    assert_workflow_assignees_ready(db, REF_TYPE, submitter_id=requester_id)

    row = MissionRequest(
        requester_id=requester_id,
        destination=destination.strip(),
        reason=reason.strip(),
        vehicle=vehicle.strip(),
        status=STATUS_PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    wf_payload: dict = {
        "ref_type": REF_TYPE,
        "ref_id": row.id,
        "submitter_id": requester_id,
    }
    if assignees_by_order:
        wf_payload["assignees_by_order"] = assignees_by_order

    try:
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        db.rollback()
        raise
    publish_event("workflow.start", wf_payload)

    return _serialize(db, row)


def on_workflow_approved(db: Session, mission_id: int) -> None:
    row = db.get(MissionRequest, mission_id)
    if not row:
        return
    row.status = STATUS_APPROVED
    db.commit()


def on_workflow_rejected(db: Session, mission_id: int) -> None:
    row = db.get(MissionRequest, mission_id)
    if not row:
        return
    row.status = STATUS_REJECTED
    db.commit()


def on_report_workflow_approved(db: Session, mission_id: int) -> None:
    row = db.get(MissionRequest, mission_id)
    if not row:
        return
    row.status = STATUS_COMPLETED
    row.updated_at = datetime.utcnow()
    db.commit()


def on_report_workflow_rejected(db: Session, mission_id: int) -> None:
    """رد کامل تأیید گزارش → امکان اصلاح و ارسال مجدد."""
    row = db.get(MissionRequest, mission_id)
    if not row:
        return
    row.status = STATUS_APPROVED
    row.updated_at = datetime.utcnow()
    db.commit()


def submit_mission_report(
    db: Session,
    mission_id: int,
    user_id: int,
    *,
    report_text: str,
) -> dict:
    row = db.get(MissionRequest, mission_id)
    if not row:
        raise ValueError("درخواست ماموریت یافت نشد")
    if row.requester_id != user_id:
        raise ValueError("فقط درخواست‌کننده می‌تواند گزارش ثبت کند")
    if row.status == STATUS_REPORT_PENDING_APPROVAL:
        raise ValueError("گزارش این ماموریت در حال تأیید است")
    if row.status == STATUS_COMPLETED:
        raise ValueError("گزارش این ماموریت قبلاً تأیید شده است")
    if row.status != STATUS_APPROVED:
        raise ValueError("فقط پس از تأیید نهایی می‌توانید گزارش ماموریت ثبت کنید")

    text = report_text.strip()
    if not text:
        raise ValueError("متن گزارش الزامی است")

    row.report_text = text
    row.reported_at = datetime.utcnow()
    row.status = STATUS_REPORT_PENDING_APPROVAL
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    assert_workflow_assignees_ready(
        db,
        WORKFLOW_REF_MISSION_REPORT,
        submitter_id=row.requester_id,
    )
    wf_payload = {
        "ref_type": WORKFLOW_REF_MISSION_REPORT,
        "ref_id": row.id,
        "submitter_id": row.requester_id,
        "requester_id": row.requester_id,
    }
    try:
        start_workflow_instance(db, wf_payload, sync_notify=True)
    except ValueError:
        row.status = STATUS_APPROVED
        db.commit()
        raise
    publish_event("workflow.start", wf_payload)
    db.refresh(row)
    return _serialize(db, row)


def get_mission_request(db: Session, request_id: int, user) -> dict:
    row = db.get(MissionRequest, request_id)
    if not row:
        raise ValueError("درخواست ماموریت یافت نشد")
    if not user_can_access_mission_request_extended(db, user, row):
        from app.models.workflow_step import WorkflowStep

        instances = _workflow_instances_for_mission(db, request_id)
        if not instances:
            raise ValueError("access denied")
        allowed = False
        for inst in instances:
            steps = db.query(WorkflowStep).filter_by(instance_id=inst.id).all()
            if any(user_can_act_on_workflow_step(user, st) for st in steps):
                allowed = True
                break
        if not allowed:
            raise ValueError("access denied")
    return _serialize(db, row)


def get_mission_request_by_workflow_instance(
    db: Session, instance_id: int, user
) -> dict:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type not in (REF_TYPE, WORKFLOW_REF_MISSION_REPORT):
        raise ValueError("درخواست ماموریت برای این نمونه workflow یافت نشد")
    return get_mission_request(db, inst.ref_id, user)


def get_mission_request_list_capabilities(db: Session, viewer: User) -> dict:
    return {"scopes": list_mission_request_available_scopes(db, viewer)}


def list_mission_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    search: str | None = None,
) -> list[dict]:
    resolved_scope = assert_scope_allowed(db, viewer, scope)
    query = db.query(MissionRequest)
    query = apply_mission_request_list_scope(
        db, query, user=viewer, scope=resolved_scope
    )
    query = apply_search_filter(
        query, MissionRequest, search, ["destination", "reason", "vehicle", "status"]
    )
    query = apply_sort(query, MissionRequest, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    ids = [r.id for r in rows]
    att_counts = count_attachments_batch(db, ENTITY_MISSION_REQUEST, ids)
    return [
        _serialize(
            db,
            r,
            include_attachments=False,
            attachment_count_override=att_counts.get(r.id, 0),
        )
        for r in rows
    ]


def count_mission_requests(
    db: Session,
    *,
    viewer: User,
    scope: str | None = None,
    search: str | None = None,
) -> int:
    resolved_scope = assert_scope_allowed(db, viewer, scope)
    query = db.query(func.count(MissionRequest.id))
    query = apply_mission_request_list_scope(
        db, query, user=viewer, scope=resolved_scope
    )
    query = apply_search_filter(
        query, MissionRequest, search, ["destination", "reason", "vehicle", "status"]
    )
    return query.scalar() or 0


def delete_mission_request(db: Session, request_id: int, user_id: int) -> None:
    row = db.get(MissionRequest, request_id)
    if not row:
        raise ValueError("درخواست ماموریت یافت نشد")
    if row.requester_id != user_id:
        raise ValueError("access denied")
    if row.status != STATUS_PENDING:
        raise ValueError("فقط درخواست در انتظار تأیید قابل حذف است")
    cancel_workflow_for_ref(db, REF_TYPE, request_id)
    cancel_workflow_for_ref(db, WORKFLOW_REF_MISSION_REPORT, request_id)
    delete_all_for_entity(db, ENTITY_MISSION_REQUEST, request_id)
    db.delete(row)
    db.commit()
