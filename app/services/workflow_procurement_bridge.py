from app.constants.procurement import (
    WORKFLOW_REF_PROFORMA,
    WORKFLOW_REF_PURCHASE,
    WORKFLOW_REF_REQUEST,
)
from app.models.request import Request
from app.services.procurement.purchase_request_service import mark_request_phase1_approved
from app.services.procurement.proforma_service import mark_proforma_workflow_approved
from app.services.procurement.request_handler import handle_request_approved


def on_pr_approved(db, payload: dict):
    ref_type = payload.get("ref_type")
    request_id = payload.get("ref_id")
    if request_id is None:
        return

    if ref_type == "payment_request":
        from app.services.procurement.procurement_payment_service import (
            on_procurement_payment_workflow_approved,
        )

        on_procurement_payment_workflow_approved(db, int(request_id))
        return

    if ref_type == WORKFLOW_REF_PURCHASE:
        return

    if ref_type == WORKFLOW_REF_PROFORMA:
        proforma_id = payload.get("proforma_id")
        if proforma_id is not None:
            try:
                proforma_id = int(proforma_id)
            except (TypeError, ValueError):
                proforma_id = None
        mark_proforma_workflow_approved(
            db,
            int(request_id),
            proforma_id,
            payment_method=payload.get("payment_method"),
            payment_comment=payload.get("comment"),
        )
        return

    if ref_type not in (None, WORKFLOW_REF_REQUEST):
        return

    request = db.get(Request, request_id)
    if not request:
        return

    if request.type == "internal":
        handle_request_approved(
            db=db,
            request_id=request_id,
            user_id=payload.get("user_id"),
        )
        return

    if request.type == "purchase":
        mark_request_phase1_approved(db, int(request_id))
