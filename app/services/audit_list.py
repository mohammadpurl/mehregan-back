"""لیست لاگ ممیزی برای ادمین."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.query_utils import apply_equal_filter, apply_search_filter, apply_sort


def _user_display(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def serialize_audit_row(db: Session, row: AuditLog) -> dict:
    actor = db.get(User, row.user_id)
    old_data = None
    new_data = None
    if row.old_data:
        try:
            old_data = json.loads(row.old_data)
        except json.JSONDecodeError:
            old_data = row.old_data
    if row.new_data:
        try:
            new_data = json.loads(row.new_data)
        except json.JSONDecodeError:
            new_data = row.new_data
    return {
        "id": row.id,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "action": row.action,
        "user_id": row.user_id,
        "user_name": _user_display(actor),
        "old_data": old_data,
        "new_data": new_data,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_audit_logs(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "id",
    sort_order: str = "desc",
    entity: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    search: str | None = None,
) -> list[dict]:
    query = db.query(AuditLog)
    if entity:
        query = query.filter(AuditLog.entity == entity.strip())
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action.strip())
    query = apply_search_filter(query, AuditLog, search, ["entity", "action"])
    query = apply_sort(query, AuditLog, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [serialize_audit_row(db, r) for r in rows]


def count_audit_logs(
    db: Session,
    *,
    entity: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    search: str | None = None,
) -> int:
    from sqlalchemy import func

    query = db.query(func.count(AuditLog.id))
    if entity:
        query = query.filter(AuditLog.entity == entity.strip())
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action.strip())
    query = apply_search_filter(query, AuditLog, search, ["entity", "action"])
    return query.scalar() or 0
