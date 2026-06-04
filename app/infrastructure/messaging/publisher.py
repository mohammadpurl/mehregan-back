import logging

from app.core.rabbitmq import rabbitmq

logger = logging.getLogger(__name__)

WORKFLOW_SYNC_FALLBACK_EVENTS = frozenset(
    {
        "workflow.start",
        "workflow.next_step",
        "workflow.approved",
        "workflow.rejected",
        "sla.breached",
        "sla.escalated",
        "sla.overdue",
    }
)


def _run_sync_fallback(event_type: str, payload: dict) -> None:
    from app.infrastructure.messaging.consumer import handle_event

    logger.warning(
        "RabbitMQ unavailable; processing event synchronously: %s",
        event_type,
    )
    handle_event(event_type, payload)


def publish_event(event_type: str, payload: dict):
    try:
        rabbitmq.publish(event_type, payload)
    except Exception as exc:
        logger.exception("Failed to publish event %s: %s", event_type, exc)
        if event_type in WORKFLOW_SYNC_FALLBACK_EVENTS:
            _run_sync_fallback(event_type, payload)
        else:
            raise


def publish_event_sync(event_type: str, payload: dict):
    publish_event(event_type, payload)
