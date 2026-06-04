from sqlalchemy.orm import Session
from datetime import datetime

from app.models.procurement import PurchaseRequisition
from app.infrastructure.messaging.publisher import publish_event


# =========================
# CREATE PR
# =========================
def create_requisition(db: Session, requester_id: int, items: list):

    pr = PurchaseRequisition(
        requester_id=requester_id, status="draft", created_at=datetime.utcnow()
    )

    db.add(pr)
    db.flush()

    # items should be saved (pseudo)
    # for item in items: create PRItem

    return pr


# =========================
# SUBMIT PR → WORKFLOW START
# =========================
def submit_requisition(db: Session, pr_id: int):

    pr = db.get(PurchaseRequisition, pr_id)

    pr.status = "pending"

    db.commit()

    publish_event(
        "procurement.requisition.submitted",
        {"pr_id": pr.id, "user_id": pr.requester_id},
    )
