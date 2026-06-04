import logging
import time
from datetime import datetime

from app.core.database import SessionLocal
from app.models.ad_hoc_task import STATUS_CLOSED, AdHocTask
from app.models.sla_record import SLARecord
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_step import WorkflowStep
from app.services.sla import is_current_pending_step
from app.services.sla_notifications import (
    notify_ad_hoc_task_sla_breach,
    notify_workflow_sla_breach,
)

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60


def process_workflow_sla(db, now: datetime) -> None:
    slas = (
        db.query(SLARecord)
        .filter(SLARecord.is_triggered == False, SLARecord.due_at < now)  # noqa: E712
        .all()
    )

    for sla in slas:
        step = db.get(WorkflowStep, sla.step_id)
        if not step or step.status != "pending":
            sla.is_triggered = True
            continue

        if not is_current_pending_step(db, step):
            sla.is_triggered = True
            continue

        inst = db.get(WorkflowInstance, sla.ref_id)
        if not inst or inst.status in ("approved", "rejected", "cancelled"):
            sla.is_triggered = True
            continue

        sla.is_triggered = True
        try:
            notify_workflow_sla_breach(db, instance=inst, step=step)
        except Exception:
            logger.exception(
                "Failed workflow SLA breach notification instance=%s step=%s",
                inst.id,
                step.id,
            )


def process_ad_hoc_sla(db, now: datetime) -> None:
    overdue = (
        db.query(AdHocTask)
        .filter(
            AdHocTask.status != STATUS_CLOSED,
            AdHocTask.due_at.isnot(None),
            AdHocTask.due_at < now,
            AdHocTask.sla_notified == False,  # noqa: E712
        )
        .all()
    )

    for task in overdue:
        task.sla_notified = True
        try:
            notify_ad_hoc_task_sla_breach(db, task)
        except Exception:
            logger.exception("Failed ad-hoc SLA breach notification task=%s", task.id)


def process_sla() -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        process_workflow_sla(db, now)
        process_ad_hoc_sla(db, now)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("SLA worker cycle failed")
    finally:
        db.close()


def start_worker() -> None:
    logger.info("SLA Worker started (interval=%ss)", CHECK_INTERVAL)
    while True:
        process_sla()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    start_worker()
