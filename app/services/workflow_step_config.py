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

_CEO_ALIASES = frozenset({"ceo", "managing_director", "مدیرعامل"})


def is_ceo_role_step(step_cfg: dict) -> bool:
    aliases = {str(a).strip().lower() for a in (step_cfg.get("role_aliases") or [])}
    return bool(aliases & _CEO_ALIASES)


def should_skip_redundant_step(
    db: Session,
    step: dict,
    *,
    role_id: int,
    submitter_id: int | None,
    override_user_id: int | None = None,
    exclude_user_ids: list[int] | None = None,
    prev_user_id: int | None = None,
) -> bool:
    """
    اگر تأییدکنندهٔ مرحلهٔ قبل تنها کسی باشد که نقش این مرحله را دارد،
    مرحله را تکراری بدان و رد کن (مثلاً مدیر مستقیم = تنها مدیرعامل/super-admin).

    ترجیح جدید: معمولاً هر دو مرحله ساخته می‌شوند و در approve با auto-skip
    یک‌بار تأیید می‌شوند؛ این تابع برای سازگاری نگه داشته شده است.
    """
    if not exclude_user_ids and not prev_user_id:
        return False
    exclude = list(exclude_user_ids or [])
    if prev_user_id is not None and prev_user_id not in exclude:
        exclude.append(prev_user_id)
    if not exclude:
        return False

    with_exclude = resolve_step_assignee_user(
        db,
        step,
        role_id=role_id,
        submitter_id=submitter_id,
        override_user_id=override_user_id,
        exclude_user_ids=exclude,
    )
    if with_exclude is not None:
        return False

    without_exclude = resolve_step_assignee_user(
        db,
        step,
        role_id=role_id,
        submitter_id=submitter_id,
        override_user_id=override_user_id,
        exclude_user_ids=None,
    )
    return without_exclude is not None and without_exclude.id in set(exclude)


def should_skip_missing_manager_step(
    db: Session,
    step: dict,
    *,
    submitter_id: int | None,
) -> bool:
    """
    مرحلهٔ submitter_manager وقتی مدیر مستقیم ثبت نشده/غیرفعال است رد می‌شود
    (مثلاً مدیرعامل که manager_id ندارد) تا گردش با مراحل بعدی ادامه یابد.
    """
    strategy = (step.get("assignee_strategy") or ROLE_POOL).strip().lower()
    if strategy != SUBMITTER_MANAGER:
        return False
    if submitter_id is None:
        return True
    from app.services.org import get_user_manager

    manager = get_user_manager(db, int(submitter_id))
    return manager is None or not manager.is_active


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


def _build_role_name_by_id(db: Session) -> dict[int, str]:
    return {
        r.id: r.name
        for r in db.query(Role).all()
        if r.id is not None and r.name
    }


def canonicalize_role_aliases(db: Session, aliases: list[str]) -> list[str]:
    """
    هر alias (name یا برچسب فارسی) را به Role.name پایدار تبدیل می‌کند و تکراری‌ها را حذف می‌کند.
    برچسب‌های فارسی ذخیره‌شده در تعریف نباید بعد از تغییر نقش در UI دوباره به نقش قبلی resolve شوند.
    """
    role_id_by_alias = _build_role_id_by_alias(db)
    role_name_by_id = _build_role_name_by_id(db)
    out: list[str] = []
    seen: set[int] = set()
    for alias in aliases:
        key = str(alias).strip().lower()
        if not key:
            continue
        rid = role_id_by_alias.get(key)
        if rid is None or rid in seen:
            continue
        name = role_name_by_id.get(rid)
        if not name:
            continue
        seen.add(rid)
        out.append(name)
    if not out:
        raise ValueError(
            "هیچ نقش معتبری در role_aliases یافت نشد. "
            "فقط نقش‌های موجود در سیستم را انتخاب کنید."
        )
    return out


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


def _active_users_with_roles(
    db: Session,
    role_ids: list[int],
    *,
    only_user_ids: set[int] | None = None,
) -> list[User]:
    if not role_ids:
        return []
    q = (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(
            UserRole.role_id.in_(role_ids),
            UserRole.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
        .distinct()
    )
    if only_user_ids is not None:
        if not only_user_ids:
            return []
        q = q.filter(User.id.in_(only_user_ids))
    return q.all()


def format_missing_role_assignee_error(
    db: Session,
    step: dict,
    role_id: int,
    *,
    exclude_user_ids: list[int] | None = None,
    submitter_id: int | None = None,
) -> str:
    from app.models.role import Role

    _ = role_id
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
        return _format_missing_manager_error(db, label=label, submitter_id=submitter_id)
    if strategy == DEPARTMENT_HEAD:
        return (
            f"برای «{label}» مسئول واحد سازمانی درخواست‌دهنده یافت نشد. "
            "واحد کاربر و «مسئول واحد» را در ساختار سازمانی بررسی کنید."
        )
    aliases = ", ".join(step.get("role_aliases") or []) or role_name
    roles_hint = " یا ".join(dict.fromkeys(role_names)) if len(role_names) > 1 else role_name
    excluded = set(exclude_user_ids or [])
    excluded_holders = _active_users_with_roles(db, role_ids, only_user_ids=excluded)
    if excluded_holders:
        names = "، ".join((u.username or f"user#{u.id}") for u in excluded_holders)
        return (
            f"برای «{label}» کاربر فعالی با نقش «{roles_hint}» هست ({names})، "
            "اما چون در مرحلهٔ قبل تأییدکننده بوده نمی‌تواند مرحلهٔ بعد هم باشد "
            "(دو مرحلهٔ پشت‌سرهم نباید به یک نفر برسد). "
            "یا مدیر مستقیم درخواست‌دهنده را به فرد دیگری تغییر دهید، "
            "یا نقش ceo را علاوه بر این کاربر به یک نفر دیگر هم بدهید."
        )
    all_holders = _active_users_with_roles(db, role_ids)
    if not all_holders:
        ceo_hint = is_ceo_role_step(step)
        tip = (
            "در مدیریت → کاربران نقش با شناسه فنی «ceo» را به‌صورت فعال به کاربر بدهید "
            "(managing_director / مدیرعامل هم قابل قبول است)."
            if ceo_hint
            else "در مدیریت → کاربران یکی از نقش‌های این مرحله را به حداقل یک کاربر فعال بدهید."
        )
        return (
            f"برای «{label}» هیچ کاربر فعالی با نقش «{roles_hint}» یافت نشد "
            f"(نقش‌های مجاز: {aliases}). {tip}"
        )
    names = "، ".join((u.username or f"user#{u.id}") for u in all_holders)
    return (
        f"برای «{label}» تخصیص تأییدکننده با نقش «{roles_hint}» ممکن نشد "
        f"(کاربران دارای نقش: {names}). تعریف گردش‌کار را بررسی کنید."
    )


def _user_label(user: User | None) -> str:
    if not user:
        return "کاربر"
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and str(p).strip())
    if name and user.username:
        return f"{name} ({user.username})"
    return name or user.username or f"user#{user.id}"


def _format_missing_manager_error(
    db: Session,
    *,
    label: str,
    submitter_id: int | None,
) -> str:
    """پیام دقیق وقتی استراتژی submitter_manager به‌خاطر نبودن/غیرفعال بودن manager_id شکست می‌خورد."""
    how_to_fix = (
        "از مسیر مدیریت → کاربران، کاربر درخواست‌دهنده را باز کنید و فیلد «مدیر مستقیم» را "
        "روی یک کاربر فعال تنظیم کنید؛ سپس دوباره درخواست را ثبت کنید."
    )
    if submitter_id is None:
        return (
            f"برای «{label}» شناسهٔ درخواست‌دهنده مشخص نیست؛ "
            "نمی‌توان مدیر مستقیم را پیدا کرد. " + how_to_fix
        )

    submitter = db.get(User, submitter_id)
    if not submitter:
        return (
            f"برای «{label}» درخواست‌دهنده (id={submitter_id}) در سیستم یافت نشد. "
            + how_to_fix
        )

    who = _user_label(submitter)
    if not submitter.manager_id:
        return (
            f"برای «{label}» کاربر «{who}» فیلد «مدیر مستقیم» ندارد "
            f"(users.manager_id خالی است). "
            "بدون تعیین مدیر مستقیم، این مرحلهٔ گردش‌کار قابل شروع نیست. "
            + how_to_fix
        )

    manager = db.get(User, submitter.manager_id)
    if not manager:
        return (
            f"برای «{label}» مدیر مستقیم ثبت‌شده برای «{who}» "
            f"(manager_id={submitter.manager_id}) در سیستم وجود ندارد. "
            + how_to_fix
        )
    if not manager.is_active:
        mgr = _user_label(manager)
        return (
            f"برای «{label}» مدیر مستقیم «{who}» یعنی «{mgr}» غیرفعال است. "
            "مدیر را فعال کنید یا مدیر مستقیم دیگری برای درخواست‌دهنده انتخاب کنید. "
            + how_to_fix
        )

    return (
        f"برای «{label}» تخصیص مدیر مستقیم برای «{who}» ممکن نشد. "
        + how_to_fix
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
