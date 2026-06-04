"""
Normalize workflow step config and resolve approvers per step.

Legacy format: [["finance_manager", "مدیر مالی"], ["ceo"]]
New format: [{"role_aliases": [...], "assignee_strategy": "fixed_user", "assignee_user_id": 5}]
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.constants.role_labels import role_display_name

ROLE_POOL = "role_pool"
FIXED_USER = "fixed_user"
# legacy — در normalize به role_pool تبدیل می‌شوند
SUBMITTER_MANAGER = "submitter_manager"
DEPARTMENT_HEAD = "department_head"

ASSIGNEE_STRATEGIES = frozenset(
    {ROLE_POOL, FIXED_USER, SUBMITTER_MANAGER, DEPARTMENT_HEAD}
)
WORKFLOW_STRATEGIES_UI = frozenset({ROLE_POOL, FIXED_USER})


def _coerce_step_raw(raw: Any) -> Any:
    """Accept dict, legacy alias list, or Pydantic step model from request body."""
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    return raw


def normalize_step(raw: Any, *, order: int) -> dict:
    raw = _coerce_step_raw(raw)
    if isinstance(raw, list):
        aliases = [str(a).strip() for a in raw if str(a).strip()]
        if not aliases:
            raise ValueError(f"step {order}: role_aliases required")
        return {
            "order": order,
            "role_aliases": aliases,
            "assignee_strategy": ROLE_POOL,
            "assignee_user_id": None,
            "label": None,
        }

    if not isinstance(raw, dict):
        raise ValueError(f"step {order}: invalid step config")

    aliases = (
        raw.get("role_aliases")
        or raw.get("roleAliases")
        or raw.get("roles")
        or []
    )
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = [str(a).strip() for a in aliases if str(a).strip()]
    if not aliases:
        raise ValueError(f"step {order}: role_aliases required")

    strategy = str(
        raw.get("assignee_strategy") or raw.get("assigneeStrategy") or ROLE_POOL
    ).strip().lower()
    if strategy not in ASSIGNEE_STRATEGIES:
        raise ValueError(f"step {order}: unknown assignee_strategy {strategy}")

    assignee_user_id = raw.get("assignee_user_id")
    if assignee_user_id is None:
        assignee_user_id = raw.get("assigneeUserId")
    if assignee_user_id in ("", None):
        assignee_user_id = None
    elif assignee_user_id is not None:
        assignee_user_id = int(assignee_user_id)

    step_action = raw.get("step_action") or raw.get("stepAction")
    if step_action is not None:
        step_action = str(step_action).strip() or None

    return {
        "order": int(raw.get("order") or order),
        "role_aliases": aliases,
        "assignee_strategy": strategy,
        "assignee_user_id": assignee_user_id,
        "label": raw.get("label"),
        "step_action": step_action,
    }


def normalize_steps_config(raw_steps: list) -> list[dict]:
    if not raw_steps:
        raise ValueError("steps must be a non-empty list")
    parsed = [normalize_step(step, order=i) for i, step in enumerate(raw_steps, start=1)]
    parsed.sort(key=lambda s: s["order"])
    return [{**step, "order": idx} for idx, step in enumerate(parsed, start=1)]


def get_step_config_at_order(db: Session, ref_type: str, order: int) -> dict | None:
    """مرحلهٔ تعریف‌شده در موقعیت order (۱-based) پس از نرمال‌سازی."""
    from app.services.workflow_definition_service import get_steps_config

    steps = get_steps_config(db, ref_type)
    idx = order - 1
    if 0 <= idx < len(steps):
        return steps[idx]
    return None


def get_step_display_label(
    db: Session,
    ref_type: str,
    order: int,
    *,
    role_name: str | None = None,
) -> str:
    """برچسب نمایشی مرحله از تعریف workflow (نه برچسب ثابت سخت‌کد)."""
    cfg = get_step_config_at_order(db, ref_type, order)
    if cfg:
        label = (cfg.get("label") or "").strip()
        if label:
            return label
        aliases = cfg.get("role_aliases") or []
        if aliases:
            return str(aliases[0])
    if role_name:
        return role_name
    return f"مرحله {order}"


def _build_role_id_by_alias(db: Session) -> dict[str, int]:
    role_id_by_name: dict[str, int] = {}
    for r in db.query(Role).all():
        if r.name:
            role_id_by_name[r.name.strip().lower()] = r.id
        label = role_display_name(
            r.name, getattr(r, "display_name", None)
        ).strip().lower()
        if label:
            role_id_by_name[label] = r.id
    return role_id_by_name


def resolve_role_ids_for_step(db: Session, step: dict) -> list[int]:
    """همه نقش‌های منطبق با role_aliases (OR) — حداقل یکی الزامی."""
    role_id_by_name = _build_role_id_by_alias(db)
    if not role_id_by_name:
        raise ValueError("هیچ نقشی در سیستم تعریف نشده است")

    resolved: list[int] = []
    unknown: list[str] = []
    for alias in step["role_aliases"]:
        key = str(alias).strip().lower()
        candidate = role_id_by_name.get(key)
        if candidate:
            if candidate not in resolved:
                resolved.append(candidate)
        else:
            unknown.append(str(alias).strip())

    if not resolved:
        aliases = "، ".join(step["role_aliases"])
        raise ValueError(
            f"هیچ نقش معتبری برای مرحله {step.get('order')} یافت نشد "
            f"(نام‌های ناشناخته: {aliases}). نقش را از لیست نقش‌های سیستم انتخاب کنید."
        )
    return resolved


def resolve_role_id_for_step(db: Session, step: dict) -> int:
    """شناسه نقش اصلی مرحله (اولین تطابق) — برای FK در workflow_steps."""
    return resolve_role_ids_for_step(db, step)[0]


def user_has_any_active_role(db: Session, user_id: int, role_ids: list[int]) -> bool:
    if not role_ids:
        return False
    return (
        db.query(UserRole.id)
        .filter(
            UserRole.user_id == user_id,
            UserRole.role_id.in_(role_ids),
            UserRole.is_active == True,  # noqa: E712
        )
        .first()
        is not None
    )


def _resolve_department_head_user_id(db: Session, submitter_id: int | None) -> int | None:
    if submitter_id is None:
        return None
    submitter = db.get(User, submitter_id)
    if not submitter or not submitter.department_id:
        return None
    from app.models.department import Department

    dept = db.get(Department, submitter.department_id)
    if not dept or not dept.head_user_id:
        return None
    return int(dept.head_user_id)


def _resolve_context_assignee_user(
    db: Session,
    *,
    strategy: str,
    submitter_id: int | None,
    role_ids: list[int],
    excluded: set[int],
) -> User | None:
    """Resolve submitter_manager / department_head to a concrete active user."""
    from app.services.org import get_user_manager

    if strategy == SUBMITTER_MANAGER:
        if submitter_id is None:
            return None
        manager = get_user_manager(db, submitter_id)
        if not manager or not manager.is_active or manager.id in excluded:
            return None
        if user_has_any_active_role(db, manager.id, role_ids):
            return manager
        # خط مدیریت مستقیم مهم‌تر از داشتن نقش در role_aliases است
        return manager

    if strategy == DEPARTMENT_HEAD:
        head_id = _resolve_department_head_user_id(db, submitter_id)
        if head_id is None:
            return None
        head = db.get(User, head_id)
        if not head or not head.is_active or head.id in excluded:
            return None
        if user_has_any_active_role(db, head.id, role_ids):
            return head
        return head

    return None


def resolve_step_preferred_user_id(
    db: Session,
    step: dict,
    *,
    submitter_id: int | None,
    override_user_id: int | None = None,
) -> int | None:
    if override_user_id is not None:
        return override_user_id

    strategy = step.get("assignee_strategy") or ROLE_POOL
    if strategy == FIXED_USER:
        uid = step.get("assignee_user_id")
        return int(uid) if uid is not None else None

    if strategy == SUBMITTER_MANAGER:
        from app.services.org import get_user_manager

        if submitter_id is None:
            return None
        manager = get_user_manager(db, submitter_id)
        return manager.id if manager else None

    if strategy == DEPARTMENT_HEAD:
        return _resolve_department_head_user_id(db, submitter_id)

    return None


def _build_exclude_user_ids(
    db: Session,
    *,
    submitter_id: int | None,
    exclude_user_ids: list[int] | None,
) -> set[int]:
    """فقط تأییدکنندگان مراحل قبلی — بدون حذف خودکار مسئول واحد/مدیر درخواست‌کننده."""
    _ = submitter_id  # reserved for future rules; do not auto-exclude dept head
    return set(exclude_user_ids or [])


def format_missing_role_assignee_error(db: Session, step: dict, role_id: int) -> str:
    from app.models.role import Role

    label = step.get("label")
    if not label:
        aliases = step.get("role_aliases") or []
        label = aliases[0] if aliases else f"مرحله {step.get('order')}"
    role_ids = resolve_role_ids_for_step(db, step)
    role_names: list[str] = []
    for rid in role_ids:
        role = db.get(Role, rid)
        role_names.append(
            role_display_name(
                role.name if role and role.name else None,
                getattr(role, "display_name", None) if role else None,
            )
        )
    role_name = role_names[0] if role_names else "—"
    strategy = step.get("assignee_strategy") or ROLE_POOL
    if strategy == FIXED_USER:
        return (
            f"برای «{label}» کاربر تأییدکننده مشخص نشده یا کاربر غیرفعال است. "
            "در تعریف گردش‌کار، استراتژی «شخص مشخص» و یک کاربر را انتخاب کنید."
        )
    if strategy == SUBMITTER_MANAGER:
        return (
            f"برای «{label}» مدیر مستقیم درخواست‌دهنده در سیستم ثبت نشده یا غیرفعال است. "
            "در مدیریت → کاربران، فیلد «مدیر مستقیم» را برای کاربر درخواست‌دهنده تنظیم کنید."
        )
    if strategy == DEPARTMENT_HEAD:
        return (
            f"برای «{label}» مسئول واحد سازمانی درخواست‌دهنده یافت نشد. "
            "واحد کاربر و «مسئول واحد» را در ساختار سازمانی بررسی کنید."
        )
    aliases = ", ".join(step.get("role_aliases") or []) or role_name
    roles_hint = " یا ".join(dict.fromkeys(role_names)) if len(role_names) > 1 else role_name
    return (
        f"برای «{label}» هیچ کاربر فعالی با نقش «{roles_hint}» یافت نشد "
        f"(نقش‌های مجاز: {aliases}). "
        "در بخش مدیریت → کاربران، نقش ceo/مدیرعامل را به‌صورت فعال به کاربر اختصاص دهید؛ "
        "اگر فقط «مدیر عامل (قدیمی)» فعال است، همان نقش ceo را فعال کنید."
    )


def resolve_step_assignee_user(
    db: Session,
    step: dict,
    *,
    role_id: int,
    submitter_id: int | None,
    override_user_id: int | None = None,
    exclude_user_ids: list[int] | None = None,
):
    """تأییدکننده بر اساس استراتژی مرحله (نقش، شخص ثابت، مدیر مستقیم، مسئول واحد)."""
    from app.services.assignment import resolve_assignee_for_role

    role_ids = resolve_role_ids_for_step(db, step)
    strategy = step.get("assignee_strategy") or ROLE_POOL

    excluded = _build_exclude_user_ids(
        db, submitter_id=submitter_id, exclude_user_ids=exclude_user_ids
    )

    preferred = resolve_step_preferred_user_id(
        db,
        step,
        submitter_id=submitter_id,
        override_user_id=override_user_id,
    )

    if strategy in (SUBMITTER_MANAGER, DEPARTMENT_HEAD):
        context_user = _resolve_context_assignee_user(
            db,
            strategy=strategy,
            submitter_id=submitter_id,
            role_ids=role_ids,
            excluded=excluded,
        )
        if context_user is not None:
            return context_user
        return None

    if strategy == FIXED_USER:
        if preferred is None:
            return None
        user = db.get(User, preferred)
        if not user or not user.is_active:
            return None
        if excluded and user.id in excluded:
            return None
        if not user_has_any_active_role(db, user.id, role_ids):
            return None
        return user

    for rid in role_ids:
        assignee = resolve_assignee_for_role(
            db,
            rid,
            preferred,
            exclude_user_ids=excluded,
            trust_preferred_without_role=False,
        )
        if assignee is not None:
            return assignee

    return None


def serialize_step_for_api(step: dict, *, role_id: int | None = None) -> dict:
    """snake_case for Pydantic models; camelCase via response serialization_alias."""
    return {
        "order": step["order"],
        "role_aliases": step["role_aliases"],
        "role_id": role_id,
        "assignee_strategy": step["assignee_strategy"],
        "assignee_user_id": step.get("assignee_user_id"),
        "label": step.get("label"),
    }
