from app.models.audit_log import AuditLog
from datetime import datetime


def on_any_event(event):
    log = AuditLog(
        event_name=event["name"],
        payload=str(event["payload"]),
        created_at=datetime.utcnow(),
    )

    db.add(log)
    db.commit()
