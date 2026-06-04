"""دسترسی به پیوست‌های مراحل گردش‌کار برای تأییدکنندگان و ذینفعان."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.procurement.purchase_workflow import is_purchase_workflow_ref
from app.models.attachment import Attachment
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.workflow_step_access import user_can_act_on_workflow_step

ENTITY_WORKFLOW_STEP = "workflow_step"
WORKFLOW_STEP_UPLOAD_PREFIX = "workflow_steps/"


def user_can_access_workflow_instance(db: Session, user, instance_id: int) -> bool:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst:
        return False

    if is_purchase_workflow_ref(inst.ref_type) and inst.ref_id:
        from app.services.purchase_request_list_scope import user_can_access_purchase_request

        if user_can_access_purchase_request(db, user, int(inst.ref_id)):
            return True

    if inst.ref_type == "financial_document" and inst.ref_id:
        from app.models.financial_document import FinancialDocument
        from app.services.financial_document import user_can_access_financial_document

        doc = db.get(FinancialDocument, int(inst.ref_id))
        if doc and user_can_access_financial_document(db, user, doc):
            return True

    if inst.ref_type in ("payment_request", "payment_order") and inst.ref_id:
        from app.models.payment_request import PaymentRequest
        from app.services.payment_request_access import user_can_access_payment_request

        pr = db.get(PaymentRequest, int(inst.ref_id))
        if pr and user_can_access_payment_request(db, user, pr):
            return True

    if inst.ref_type == "petty_cash" and inst.ref_id:
        try:
            from app.services.petty_cash import get_petty_cash

            get_petty_cash(db, int(inst.ref_id), user)
            return True
        except ValueError:
            pass

    if inst.ref_type == "mission_request" and inst.ref_id:
        try:
            from app.services.mission_request import get_mission_request

            get_mission_request(db, int(inst.ref_id), user)
            return True
        except ValueError:
            pass

    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.instance_id == instance_id)
        .all()
    )
    for step in steps:
        if user_can_act_on_workflow_step(user, step):
            return True
        if step.approved_by == user.id:
            return True
        if step.assigned_user_id == user.id:
            return True

    from app.services.workflow_submitter import resolve_submitter_id

    submitter_id = resolve_submitter_id(db, inst)
    return submitter_id is not None and submitter_id == user.id


def user_can_access_workflow_step_attachment(db: Session, user, att: Attachment) -> bool:
    if att.entity_type != ENTITY_WORKFLOW_STEP:
        return False
    step = db.get(WorkflowStep, att.entity_id)
    if not step:
        return False
    return user_can_access_workflow_instance(db, user, step.instance_id)
