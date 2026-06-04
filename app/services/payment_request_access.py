"""دسترسی به جزئیات درخواست پرداخت برای ثبت‌کننده و ذینفعان workflow."""

from sqlalchemy.orm import Session

from app.constants.payment_order import WORKFLOW_REF_PAYMENT_ORDER
from app.models.payment_request import PaymentRequest
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.models.user import User
from app.services.payment_request_list_scope import user_can_access_payment_request_extended

_PAYMENT_WORKFLOW_REFS = ("payment_request", WORKFLOW_REF_PAYMENT_ORDER)


def workflow_instance_for_payment(db: Session, payment_request_id: int) -> WorkflowInstance | None:
    for ref_type in _PAYMENT_WORKFLOW_REFS:
        inst = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.ref_type == ref_type,
                WorkflowInstance.ref_id == payment_request_id,
            )
            .order_by(WorkflowInstance.id.desc())
            .first()
        )
        if inst:
            return inst
    return None


def user_can_access_payment_request(db: Session, user: User, pr: PaymentRequest) -> bool:
    if user_can_access_payment_request_extended(db, user, pr):
        return True
    inst = workflow_instance_for_payment(db, pr.id)
    if not inst:
        return False
    user_role_ids = {r.id for r in user.get_roles()}
    steps = (
        db.query(WorkflowStep).filter(WorkflowStep.instance_id == inst.id).all()
    )
    for st in steps:
        if st.assigned_user_id == user.id:
            return True
        if st.role_id in user_role_ids:
            return True
    return False


def user_can_edit_payment_request_as_requester(user: User, pr: PaymentRequest) -> bool:
    return pr.requester_id == user.id


def get_payment_request_by_workflow_instance(
    db: Session, instance_id: int
) -> PaymentRequest | None:
    inst = db.get(WorkflowInstance, instance_id)
    if not inst or inst.ref_type not in _PAYMENT_WORKFLOW_REFS:
        return None
    return db.get(PaymentRequest, inst.ref_id)

