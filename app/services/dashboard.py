from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.models.inbox import InboxItem
from app.models.sla_record import SLARecord
from app.models.workflow_instance import WorkflowInstance
from app.models.request import Request
from app.models.payment_request import PaymentRequest
from app.models.warehouse_form import WarehouseForm
from app.models.workflow_form import WorkflowForm


def get_user_dashboard(db: Session, user_id: int):

    # =========================
    # TASKS
    # =========================
    tasks = (
        db.query(InboxItem)
        .filter(InboxItem.user_id == user_id)
        .order_by(InboxItem.created_at.desc())
        .limit(20)
        .all()
    )

    # =========================
    # STATS
    # =========================
    pending = (
        db.query(func.count(InboxItem.id))
        .filter(InboxItem.user_id == user_id, InboxItem.is_done == False)
        .scalar()
    )

    done = (
        db.query(func.count(InboxItem.id))
        .filter(InboxItem.user_id == user_id, InboxItem.is_done == True)
        .scalar()
    )

    # =========================
    # SLA OVERDUE
    # =========================
    now = datetime.utcnow()

    overdue = (
        db.query(func.count(SLARecord.id))
        .filter(
            SLARecord.is_triggered == False,
            SLARecord.due_at < now,
        )
        .scalar()
    )

    my_requests = (
        db.query(func.count(Request.id)).filter(Request.requester_id == user_id).scalar()
    )
    my_payment_requests = (
        db.query(func.count(PaymentRequest.id))
        .filter(PaymentRequest.requester_id == user_id)
        .scalar()
    )
    my_warehouse_forms = (
        db.query(func.count(WarehouseForm.id))
        .filter(WarehouseForm.requester_id == user_id)
        .scalar()
    )
    my_workflow_forms = (
        db.query(func.count(WorkflowForm.id))
        .filter(WorkflowForm.requester_id == user_id)
        .scalar()
    )

    return {
        "tasks": tasks,
        "stats": {
            "pending": pending,
            "done": done,
            "overdue": overdue,
            "my_requests": my_requests,
            "my_payment_requests": my_payment_requests,
            "my_warehouse_forms": my_warehouse_forms,
            "my_workflow_forms": my_workflow_forms,
        },
    }


def get_management_dashboard(db: Session):
    now = datetime.utcnow()

    total_requests = db.query(func.count(Request.id)).scalar()
    total_payment_requests = db.query(func.count(PaymentRequest.id)).scalar()
    total_warehouse_forms = db.query(func.count(WarehouseForm.id)).scalar()
    total_workflow_forms = db.query(func.count(WorkflowForm.id)).scalar()

    workflow_pending = (
        db.query(func.count(WorkflowInstance.id))
        .filter(WorkflowInstance.status == "pending")
        .scalar()
    )
    workflow_approved = (
        db.query(func.count(WorkflowInstance.id))
        .filter(WorkflowInstance.status == "approved")
        .scalar()
    )
    workflow_rejected = (
        db.query(func.count(WorkflowInstance.id))
        .filter(WorkflowInstance.status == "rejected")
        .scalar()
    )

    inbox_pending = (
        db.query(func.count(InboxItem.id)).filter(InboxItem.is_done == False).scalar()
    )
    overdue_sla = (
        db.query(func.count(SLARecord.id))
        .filter(SLARecord.is_triggered == False, SLARecord.due_at < now)
        .scalar()
    )

    total_workflows = (
        (workflow_pending or 0) + (workflow_approved or 0) + (workflow_rejected or 0)
    )
    approval_rate = (
        round(((workflow_approved or 0) / total_workflows) * 100, 2)
        if total_workflows
        else 0
    )
    rejection_rate = (
        round(((workflow_rejected or 0) / total_workflows) * 100, 2)
        if total_workflows
        else 0
    )

    workflow_by_ref_type_rows = (
        db.query(WorkflowInstance.ref_type, func.count(WorkflowInstance.id))
        .group_by(WorkflowInstance.ref_type)
        .all()
    )
    workflow_by_ref_type = {row[0]: row[1] for row in workflow_by_ref_type_rows}

    return {
        "forms": {
            "requests": total_requests,
            "payment_requests": total_payment_requests,
            "warehouse_forms": total_warehouse_forms,
            "workflow_forms": total_workflow_forms,
        },
        "workflow": {
            "total": total_workflows,
            "pending": workflow_pending,
            "approved": workflow_approved,
            "rejected": workflow_rejected,
            "approval_rate_percent": approval_rate,
            "rejection_rate_percent": rejection_rate,
            "by_ref_type": workflow_by_ref_type,
        },
        "operations": {
            "inbox_pending": inbox_pending,
            "sla_overdue": overdue_sla,
        },
    }
