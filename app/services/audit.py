import json
from typing import Any

from app.models.audit_log import AuditLog


def _dump_data(data: dict[str, Any] | None) -> str | None:
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False)


def create_audit_log(
    db,
    *,
    action: str,
    user_id: int,
    entity: str,
    entity_id: int,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
):
    log = AuditLog(
        action=action,
        user_id=user_id,
        entity=entity,
        entity_id=entity_id,
        old_data=_dump_data(old_data),
        new_data=_dump_data(new_data),
    )

    db.add(log)
    return log
