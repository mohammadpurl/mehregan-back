from sqlalchemy.orm import Session

from app.constants.procurement import (
    PURCHASE_WORKFLOW_REFS,
    REQUEST_TYPE_PURCHASE,
)
from app.models.request import Request
from app.models.role import Role
from app.models.user import User
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.models.workflow_approval import WorkflowApproval
from app.services.workflow_step_kinds import step_is_financial
from app.services.procurement.purchase_workflow import step_action_for_order
from app.services.workflow_step_config import get_step_display_label

REF_TYPE_PHASE_LABELS: dict[str, str] = {
    "purchase_request": "درخواست خرید کالا",
    "request": "تأیید درخواست خرید",
    "procurement_proforma": "تأیید پیش‌فاکتور",
    "payment_request": "تأیید پرداخت",
    "petty_cash": "تأیید تنخواه",
    "workflow_form": "تأیید درخواست اداری",
    "warehouse_form": "تأیید فرم انبار",
    "goods_receipt": "تأیید رسید انبار",
    "mission_request": "درخواست ماموریت",
    "financial_document": "سند مالی",
    "purchase_order": "سفارش خرید",
    "payment_order": "دستور پرداخت",
}


def _display_name(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def get_instance_approval_plan(db: Session, instance_id: int) -> dict | None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None

    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.instance_id == instance_id)
        .order_by(WorkflowStep.order)
        .all()
    )
    step_rows: list[dict] = []
    prev_assignee_id: int | None = None
    for st in steps:
        role = db.get(Role, st.role_id)
        assignee = (
            db.get(User, st.assigned_user_id) if st.assigned_user_id else None
        )
        approver = db.get(User, st.approved_by) if st.approved_by else None
        auto_skipped = False
        if st.status == "approved" and st.id:
            log = (
                db.query(WorkflowApproval)
                .filter(
                    WorkflowApproval.instance_id == instance_id,
                    WorkflowApproval.step_id == st.id,
                )
                .order_by(WorkflowApproval.id.desc())
                .first()
            )
            if log and log.comment and "تأیید خودکار" in log.comment:
                auto_skipped = True

        duplicate_assignee = (
            prev_assignee_id is not None
            and st.assigned_user_id is not None
            and prev_assignee_id == st.assigned_user_id
            and st.status == "pending"
        )
        role_label = (
            (role.display_name or role.name) if role else None
        )
        step_rows.append(
            {
                "id": st.id,
                "order": st.order,
                "status": st.status,
                "label": get_step_display_label(
                    db,
                    inst.ref_type,
                    st.order,
                    role_name=role_label,
                ),
                "roleId": st.role_id,
                "roleName": role_label,
                "assignedUserId": st.assigned_user_id,
                "assignedUserName": _display_name(assignee),
                "approvedBy": st.approved_by,
                "approvedByName": _display_name(approver),
                "approvedAt": st.approved_at.isoformat() if st.approved_at else None,
                "autoSkippedSameApprover": auto_skipped,
                "isFinancialStep": step_is_financial(db, inst, st),
                "duplicateAssigneeWithPrevious": duplicate_assignee,
                "stepAction": step_action_for_order(db, inst.ref_type, st.order),
            }
        )
        if st.assigned_user_id is not None:
            prev_assignee_id = st.assigned_user_id

    step_order_by_id = {st.id: st.order for st in steps}
    history_rows: list[dict] = []
    for row in (
        db.query(WorkflowApproval)
        .filter(WorkflowApproval.instance_id == instance_id)
        .order_by(WorkflowApproval.created_at)
        .all()
    ):
        actor = db.get(User, row.approved_by)
        history_rows.append(
            {
                "stepId": row.step_id,
                "stepOrder": step_order_by_id.get(row.step_id),
                "decision": row.decision,
                "comment": row.comment,
                "approvedBy": row.approved_by,
                "approvedByName": _display_name(actor),
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }
        )

    from app.services.workflow_step_attachment import collect_plan_attachments

    return {
        "instanceId": inst.id,
        "refType": inst.ref_type,
        "refId": inst.ref_id,
        "status": inst.status,
        "steps": step_rows,
        "decisions": history_rows,
        "stepAttachments": collect_plan_attachments(db, instance_id),
    }


def _phase_label(ref_type: str) -> str:
    return REF_TYPE_PHASE_LABELS.get(ref_type, ref_type_label_fallback(ref_type))


def ref_type_label_fallback(ref_type: str) -> str:
    return ref_type.replace("_", " ")


def _collect_related_instances(db: Session, inst: WorkflowInstance) -> list[WorkflowInstance]:
    """همه نمونه‌های گردش‌کار مرتبط با یک درخواست کسب‌وکار (مثلاً فاز ۱ و ۲ خرید)."""
    seen: set[int] = set()
    ordered: list[WorkflowInstance] = []

    def add(i: WorkflowInstance) -> None:
        if i.id not in seen:
            seen.add(i.id)
            ordered.append(i)

    add(inst)
    ref_id = inst.ref_id
    ref_type = inst.ref_type

    if ref_type in PURCHASE_WORKFLOW_REFS:
        for row in (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.ref_id == ref_id,
                WorkflowInstance.ref_type.in_(PURCHASE_WORKFLOW_REFS),
            )
            .order_by(WorkflowInstance.id.asc())
            .all()
        ):
            add(row)
        req = db.get(Request, ref_id)
        if req and req.type == REQUEST_TYPE_PURCHASE and req.payment_request_id:
            for row in (
                db.query(WorkflowInstance)
                .filter(
                    WorkflowInstance.ref_type == "payment_request",
                    WorkflowInstance.ref_id == req.payment_request_id,
                )
                .order_by(WorkflowInstance.id.asc())
                .all()
            ):
                add(row)
        return ordered

    if ref_type == "payment_request":
        req = (
            db.query(Request)
            .filter(
                Request.payment_request_id == ref_id,
                Request.type == REQUEST_TYPE_PURCHASE,
            )
            .first()
        )
        if req:
            for row in (
                db.query(WorkflowInstance)
                .filter(
                    WorkflowInstance.ref_id == req.id,
                    WorkflowInstance.ref_type.in_(PURCHASE_WORKFLOW_REFS),
                )
                .order_by(WorkflowInstance.id.asc())
                .all()
            ):
                add(row)
        return ordered

    return ordered


def get_approval_history_for_instance(db: Session, instance_id: int) -> dict | None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return None

    sections: list[dict] = []
    for related in _collect_related_instances(db, inst):
        plan = get_instance_approval_plan(db, related.id)
        if not plan:
            continue
        sections.append(
            {
                **plan,
                "phaseLabel": _phase_label(related.ref_type),
                "isCurrent": related.id == instance_id,
            }
        )

    return {
        "currentInstanceId": instance_id,
        "sections": sections,
    }
