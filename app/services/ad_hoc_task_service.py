"""سرویس کارهای پیش‌بینی‌نشده."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.ad_hoc_task import STATUS_CLOSED, STATUS_OPEN, AdHocTask, AdHocTaskStep
from app.models.user import User
from app.schemas.ad_hoc_task import AdHocTaskStepCreate, AdHocTaskCreate
from app.services.attachment_service import (
    ENTITY_AD_HOC_TASK,
    ENTITY_AD_HOC_TASK_STEP,
    list_attachments_serialized,
)
from app.services.inbox import create_inbox_item, mark_inbox_done_for_ad_hoc_task
from app.services.notification import create_notification
from app.services.query_utils import apply_search_filter, apply_sort


def _to_utc_naive(dt: datetime) -> datetime:
    """تبدیل به datetime بدون timezone برای مقایسه/ذخیره (UTC)."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _due_in_future(due_at: datetime) -> bool:
    return _to_utc_naive(due_at) > datetime.utcnow()

def _user_display(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def _notify_assignee(db: Session, *, assignee_id: int, task: AdHocTask, author_name: str) -> None:
    title = f"کار پیش‌بینی‌نشده: {task.title}"
    message = f"{author_name or 'کاربر'} یک کار جدید به شما ارجاع داد."
    create_inbox_item(
        db,
        role_id=None,
        title=title,
        message=message,
        ref_id=task.id,
        ref_type="ad_hoc_task",
        preferred_user_id=assignee_id,
    )
    create_notification(
        db,
        assignee_id,
        title=title,
        message=message,
        type="ad_hoc_task.assigned",
        ref_id=task.id,
        ref_type="ad_hoc_task",
    )


def _user_participated_subquery(user_id: int):
    return exists(
        select(1)
        .select_from(AdHocTaskStep)
        .where(
            AdHocTaskStep.task_id == AdHocTask.id,
            or_(
                AdHocTaskStep.author_id == user_id,
                AdHocTaskStep.assignee_id == user_id,
            ),
        )
    )


_CEO_ALL_VIEW_ROLES = frozenset(
    {
        "ceo",
        "managing_director",
        "مدیرعامل",
        "admin",
        "super-admin",
        "system_admin",
    }
)


def _resolve_user(db: Session, user: User | int) -> User | None:
    if isinstance(user, User):
        return user
    return db.get(User, int(user))


def user_can_view_all_ad_hoc_tasks(db: Session, user: User | int) -> bool:
    """مدیرعامل و دارندگان workflow.all.read همه کارهای پیش‌بینی‌نشده را می‌بینند."""
    from app.services.permission import user_has_permission_db

    user_obj = _resolve_user(db, user)
    if not user_obj:
        return False
    if user_has_permission_db(db, user_obj.id, "workflow.all.read"):
        return True
    if user_has_permission_db(db, user_obj.id, "admin.manage"):
        return True
    names = {r.name.strip().lower() for r in user_obj.get_roles() if r and r.name}
    return bool(names & _CEO_ALL_VIEW_ROLES)


def user_can_access_task(db: Session, task: AdHocTask, user: User | int) -> bool:
    user_obj = _resolve_user(db, user)
    if not user_obj:
        return False
    if user_can_view_all_ad_hoc_tasks(db, user_obj):
        return True
    user_id = user_obj.id
    if task.created_by_id == user_id or task.current_assignee_id == user_id:
        return True
    return (
        db.query(
            exists(
                select(1)
                .select_from(AdHocTaskStep)
                .where(
                    AdHocTaskStep.task_id == task.id,
                    or_(
                        AdHocTaskStep.author_id == user_id,
                        AdHocTaskStep.assignee_id == user_id,
                    ),
                )
            )
        ).scalar()
        is True
    )


def search_users_for_assign(db: Session, *, search: str | None, limit: int = 30) -> list[dict]:
    query = db.query(User).filter(User.is_active.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.username.ilike(term),
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                User.email.ilike(term),
            )
        )
    rows = query.order_by(User.first_name.asc(), User.last_name.asc()).limit(limit).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": _user_display(u),
        }
        for u in rows
    ]


def create_ad_hoc_task(db: Session, *, user_id: int, payload: AdHocTaskCreate) -> dict:
    assignee = db.get(User, payload.assignee_id)
    if not assignee or not assignee.is_active:
        raise ValueError("گیرنده کار یافت نشد یا غیرفعال است")
    if payload.assignee_id == user_id:
        raise ValueError("گیرنده نمی‌تواند خودتان باشید")
    if not _due_in_future(payload.due_at):
        raise ValueError("مهلت انجام کار باید در آینده باشد")

    due_at = _to_utc_naive(payload.due_at)
    task = AdHocTask(
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        created_by_id=user_id,
        current_assignee_id=payload.assignee_id,
        status=STATUS_OPEN,
        due_at=due_at,
        sla_notified=False,
    )
    db.add(task)
    db.flush()

    author = db.get(User, user_id)
    comment = (payload.initial_comment or payload.description or "ایجاد کار").strip()
    step = AdHocTaskStep(
        task_id=task.id,
        author_id=user_id,
        comment=comment,
        assignee_id=payload.assignee_id,
    )
    db.add(step)

    _notify_assignee(
        db,
        assignee_id=payload.assignee_id,
        task=task,
        author_name=_user_display(author) or "",
    )
    db.commit()
    db.refresh(task)

    return get_ad_hoc_task_detail(db, task.id, user_id)


def _list_query(db: Session, user: User, scope: str | None):
    query = db.query(AdHocTask)
    scope_norm = (scope or "all").strip().lower()
    user_id = user.id
    if scope_norm == "mine":
        query = query.filter(AdHocTask.created_by_id == user_id)
    elif scope_norm == "assigned":
        query = query.filter(AdHocTask.current_assignee_id == user_id)
    elif scope_norm == "all" and user_can_view_all_ad_hoc_tasks(db, user):
        # مدیرعامل / مشاهده سراسری: بدون فیلتر شخصی
        return query
    else:
        query = query.filter(
            or_(
                AdHocTask.created_by_id == user_id,
                AdHocTask.current_assignee_id == user_id,
                _user_participated_subquery(user_id),
            )
        )
    return query


def list_ad_hoc_tasks(
    db: Session,
    *,
    user: User,
    scope: str | None = None,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    search: str | None = None,
) -> list[dict]:
    query = _list_query(db, user, scope)
    query = apply_search_filter(query, AdHocTask, search, ["title", "description", "status"])
    query = apply_sort(query, AdHocTask, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    out: list[dict] = []
    for task in rows:
        creator = db.get(User, task.created_by_id)
        assignee = db.get(User, task.current_assignee_id)
        out.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "created_by_name": _user_display(creator),
                "current_assignee_name": _user_display(assignee),
                "due_at": task.due_at,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )
    return out


def count_ad_hoc_tasks(
    db: Session,
    *,
    user: User,
    scope: str | None = None,
    search: str | None = None,
) -> int:
    query = _list_query(db, user, scope)
    query = apply_search_filter(query, AdHocTask, search, ["title", "description", "status"])
    return int(query.with_entities(func.count(AdHocTask.id)).scalar() or 0)


def get_ad_hoc_task_detail(db: Session, task_id: int, user: User | int) -> dict:
    task = db.get(AdHocTask, task_id)
    if not task:
        raise ValueError("کار یافت نشد")
    if not user_can_access_task(db, task, user):
        raise ValueError("دسترسی به این کار مجاز نیست")

    creator = db.get(User, task.created_by_id)
    assignee = db.get(User, task.current_assignee_id)
    steps_out: list[dict] = []
    for step in sorted(task.steps, key=lambda s: s.id):
        author = db.get(User, step.author_id)
        step_assignee = db.get(User, step.assignee_id) if step.assignee_id else None
        steps_out.append(
            {
                "id": step.id,
                "author_id": step.author_id,
                "author_name": _user_display(author),
                "comment": step.comment,
                "assignee_id": step.assignee_id,
                "assignee_name": _user_display(step_assignee),
                "created_at": step.created_at,
                "attachments": list_attachments_serialized(
                    db, ENTITY_AD_HOC_TASK_STEP, step.id
                ),
            }
        )

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "created_by_id": task.created_by_id,
        "created_by_name": _user_display(creator),
        "current_assignee_id": task.current_assignee_id,
        "current_assignee_name": _user_display(assignee),
        "due_at": task.due_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "attachments": list_attachments_serialized(db, ENTITY_AD_HOC_TASK, task.id),
        "steps": steps_out,
    }


def add_ad_hoc_task_step(
    db: Session,
    *,
    task_id: int,
    user_id: int,
    payload: AdHocTaskStepCreate,
) -> dict:
    task = db.get(AdHocTask, task_id)
    if not task:
        raise ValueError("کار یافت نشد")
    if task.status == STATUS_CLOSED:
        raise ValueError("کار بسته شده و قابل ویرایش نیست")
    if task.current_assignee_id != user_id:
        raise ValueError("فقط گیرنده فعلی می‌تواند اقدام ثبت کند")

    assignee_id = payload.assignee_id
    if payload.close_task:
        task.status = STATUS_CLOSED
        assignee_id = None
    elif assignee_id is None:
        raise ValueError("گیرنده مرحله بعد را انتخاب کنید یا کار را ببندید")
    else:
        assignee = db.get(User, assignee_id)
        if not assignee or not assignee.is_active:
            raise ValueError("گیرنده یافت نشد")
        if payload.due_at is None:
            raise ValueError("مهلت انجام برای گیرنده بعدی الزامی است")
        if not _due_in_future(payload.due_at):
            raise ValueError("مهلت انجام کار باید در آینده باشد")
        task.current_assignee_id = assignee_id
        task.due_at = _to_utc_naive(payload.due_at)
        task.sla_notified = False

    task.updated_at = datetime.utcnow()
    author = db.get(User, user_id)
    step = AdHocTaskStep(
        task_id=task.id,
        author_id=user_id,
        comment=payload.comment.strip(),
        assignee_id=assignee_id,
    )
    db.add(step)

    mark_inbox_done_for_ad_hoc_task(db, task.id, user_id=user_id)

    if assignee_id and assignee_id != user_id:
        _notify_assignee(
            db,
            assignee_id=assignee_id,
            task=task,
            author_name=_user_display(author) or "",
        )

    db.commit()
    db.refresh(task)

    return get_ad_hoc_task_detail(db, task.id, user_id)
