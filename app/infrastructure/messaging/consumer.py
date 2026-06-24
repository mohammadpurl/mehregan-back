import json

from app.core.rabbitmq import rabbitmq_connection
from app.gateways.event_gateway import EventGateway
from app.core.database import SessionLocal
from app.infrastructure.messaging.publisher import publish_event

gateway = EventGateway()


def _aliases_matrix_to_role_ids(db, aliases_matrix: list[list[str]]) -> list[int]:
    roles = db.query(Role).all()
    if not roles:
        raise ValueError("No roles defined in system")

    role_id_by_name = {r.name.strip().lower(): r.id for r in roles if r.name}
    fallback_role_id = roles[0].id
    resolved: list[int] = []
    for aliases in aliases_matrix:
        resolved_role_id = fallback_role_id
        for alias in aliases:
            candidate = role_id_by_name.get(str(alias).strip().lower())
            if candidate:
                resolved_role_id = candidate
                break
        resolved.append(resolved_role_id)
    return resolved


def _parse_assignees_by_order(payload: dict) -> dict[int, int]:
    """1-based step order -> user id."""
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


def _start_workflow_instance(db, payload: dict):
    from app.services.workflow_start import start_workflow_instance

    start_workflow_instance(db, payload, sync_notify=True)


# ==============================
# EVENT HANDLER (ONLY ENTRY)
# ==============================
def handle_event(event, payload):

    db = SessionLocal()

    try:

        if event == "procurement.requisition.submitted":

            publish_event(
                "workflow.next_step",
                {
                    "instance_id": payload["pr_id"],
                    "role_id": 2,
                    "step_id": 1,
                },
            )
        elif event == "workflow.start":
            _start_workflow_instance(db, payload)
            print(f"Started workflow instance for payload: {payload}", flush=True)

        elif event == "workflow.approved":
            from app.services.workflow_procurement_bridge import on_pr_approved
            from app.services.workflow_petty_cash_bridge import handle_workflow_approved
            from app.services.workflow_financial_document_bridge import (
                handle_workflow_approved as handle_fd_approved,
            )
            from app.services.workflow_mission_request_bridge import (
                handle_workflow_approved as handle_mission_approved,
            )

            on_pr_approved(db, payload)
            handle_workflow_approved(db, payload)
            handle_fd_approved(db, payload)
            handle_mission_approved(db, payload)

        elif event == "workflow.rejected":
            from app.services.workflow_petty_cash_bridge import handle_workflow_rejected
            from app.services.workflow_financial_document_bridge import (
                handle_workflow_rejected as handle_fd_rejected,
            )
            from app.services.workflow_mission_request_bridge import (
                handle_workflow_rejected as handle_mission_rejected,
            )

            handle_workflow_rejected(db, payload)
            handle_fd_rejected(db, payload)
            handle_mission_rejected(db, payload)

        elif event == "workflow.next_step":
            from app.services.workflow_notifications import notify_workflow_next_step

            target = notify_workflow_next_step(db, payload)
            if target:
                print(
                    f"workflow.next_step notified user={target} instance={payload.get('instance_id')}",
                    flush=True,
                )
            else:
                print(
                    f"Skipped workflow.next_step: {payload}",
                    flush=True,
                )
        elif event in ("sla.breached", "sla.escalated", "sla.overdue"):
            from app.models.workflow_instance import WorkflowInstance
            from app.models.workflow_step import WorkflowStep
            from app.services.sla_notifications import notify_workflow_sla_breach

            inst = db.get(WorkflowInstance, payload.get("instance_id"))
            step = db.get(WorkflowStep, payload.get("step_id"))
            if inst and step:
                notify_workflow_sla_breach(db, instance=inst, step=step)
        else:
            print(f"Unhandled event: {event}", flush=True)

        db.commit()
        print(f"Committed event: {event}", flush=True)

    finally:
        db.close()


# ==============================
# RABBITMQ CALLBACK
# ==============================
def callback(ch, method, properties, body):
    try:
        data = json.loads(body.decode())
        print(f"Consumer received: {data}", flush=True)

        handle_event(
            event=data["event"],
            payload=data.get("payload", {}),
        )

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"RabbitMQ Error: {e}", flush=True)

        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# ==============================
# START CONSUMER
# ==============================
def start_consumer():
    connection = rabbitmq_connection()

    channel = connection.channel()

    channel.queue_declare(queue="erp_events", durable=True)

    channel.basic_consume(
        queue="erp_events",
        on_message_callback=callback,
        auto_ack=False,
    )

    print("ERP Consumer Started (Event Gateway Mode)")
    channel.start_consuming()


if __name__ == "__main__":
    start_consumer()
