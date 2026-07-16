from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.financial_workflow import UNIFIED_FINANCIAL_STEPS
from app.constants.mission_request import MISSION_REPORT_STEPS
from app.constants.petty_cash import PETTY_CASH_SETTLEMENT_STEPS
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition
from app.services.query_utils import apply_search_filter, apply_sort
from app.services.workflow_step_config import (
    format_missing_role_assignee_error,
    normalize_steps_config,
    resolve_role_id_for_step,
    resolve_step_assignee_user,
    serialize_step_for_api,
    should_skip_missing_manager_step,
)

_UNIFIED = list(UNIFIED_FINANCIAL_STEPS)

DEFAULT_ROLE_STEPS: dict[str, list[list[str]]] = {
    "workflow_form": [["manager", "project_manager", "مدیر پروژه"]],
    "payment_request": _UNIFIED,
    "payment_order": _UNIFIED,
    "financial_document": _UNIFIED,
    "warehouse_form": [
        ["warehouse_manager", "warehouse", "مسئول انبار"],
        ["finance_manager", "accountant", "مدیر مالی"],
        ["ceo", "managing_director", "مدیرعامل"],
    ],
    "purchase_request": [
        {
            "order": 1,
            "label": "تأیید مدیر مالی",
            "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
            "assignee_strategy": "role_pool",
            "step_action": "approval",
        },
        {
            "order": 2,
            "label": "تأیید مدیرعامل — درخواست",
            "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
            "assignee_strategy": "role_pool",
            "step_action": "approval",
        },
        {
            "order": 3,
            "label": "ثبت و ارسال پیش‌فاکتور — مسئول خرید",
            "role_aliases": [
                "purchase_officer",
                "purchase_manager",
                "مسئول خرید",
                "مدیر خرید",
            ],
            "assignee_strategy": "role_pool",
            "step_action": "upload_proforma",
        },
        {
            "order": 4,
            "label": "تأیید پیش‌فاکتور و روش پرداخت — مدیرعامل",
            "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
            "assignee_strategy": "role_pool",
            "step_action": "approve_proforma",
        },
        {
            "order": 5,
            "label": "بارگذاری فاکتور — مسئول خرید",
            "role_aliases": [
                "purchase_officer",
                "purchase_manager",
                "مسئول خرید",
                "مدیر خرید",
            ],
            "assignee_strategy": "role_pool",
            "step_action": "upload_invoice",
        },
        {
            "order": 6,
            "label": "تأیید پرداخت فاکتور — مدیر مالی",
            "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
            "assignee_strategy": "role_pool",
            "step_action": "confirm_payment",
        },
    ],
    "request": [
        {
            "order": 1,
            "label": "تأیید مدیر مالی",
            "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
            "assignee_strategy": "role_pool",
        },
        {
            "order": 2,
            "label": "تأیید مدیرعامل",
            "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
            "assignee_strategy": "role_pool",
        },
    ],
    "procurement_proforma": [
        {
            "order": 1,
            "label": "تأیید پیش‌فاکتور و روش پرداخت — مدیرعامل",
            "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
            "assignee_strategy": "role_pool",
        },
    ],
    "petty_cash": _UNIFIED,
    "petty_cash_settlement": list(PETTY_CASH_SETTLEMENT_STEPS),
    "mission_request": [
        {
            "order": 1,
            "label": "تأیید مدیر مستقیم",
            "role_aliases": ["manager", "project_manager", "مدیر مستقیم", "مدیر واحد"],
            "assignee_strategy": "submitter_manager",
        },
        {
            "order": 2,
            "label": "تأیید مدیرعامل",
            "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
            "assignee_strategy": "role_pool",
        },
    ],
    "mission_report": list(MISSION_REPORT_STEPS),
}


def get_steps_config(db: Session, ref_type: str) -> list[dict]:
    row = get_definition_by_ref_type(db, ref_type)
    if row and isinstance(row.steps_config, list) and row.steps_config:
        return normalize_steps_config(row.steps_config)
    legacy = DEFAULT_ROLE_STEPS.get(ref_type, [["manager"]])
    return normalize_steps_config(legacy)


def get_role_step_aliases(db: Session, ref_type: str) -> list[list[str]]:
    """Backward compatible alias matrix for older callers."""
    return [step["role_aliases"] for step in get_steps_config(db, ref_type)]


def list_definitions(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "id",
    sort_order: str = "desc",
    search: str | None = None,
):
    query = db.query(WorkflowDefinition)
    query = apply_search_filter(
        query, WorkflowDefinition, search, ["name", "code", "ref_type"]
    )
    query = apply_sort(query, WorkflowDefinition, sort_by, sort_order)
    return query.offset(offset).limit(limit).all()


def count_definitions(db: Session, *, search: str | None = None) -> int:
    query = db.query(func.count(WorkflowDefinition.id))
    query = apply_search_filter(
        query, WorkflowDefinition, search, ["name", "code", "ref_type"]
    )
    return query.scalar() or 0


def get_definition_by_ref_type(db: Session, ref_type: str):
    return (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.ref_type == ref_type)
        .first()
    )


def _user_display(user: User | None) -> str | None:
    if not user:
        return None
    parts = [user.first_name, user.last_name]
    name = " ".join(p.strip() for p in parts if p and p.strip())
    return name or user.username


def assert_workflow_assignees_ready(
    db: Session,
    ref_type: str,
    *,
    submitter_id: int | None,
) -> None:
    """قبل از شروع گردش: هر مرحلهٔ غیرردشده باید assignee داشته باشد."""
    preview = preview_assignees(db, ref_type, submitter_id=submitter_id)
    pending = [item for item in preview if not item.get("skipped_redundant")]
    if not pending:
        raise ValueError(
            "هیچ مرحلهٔ قابل تخصیص برای این گردش‌کار باقی نماند. "
            "تعریف workflow را بررسی کنید."
        )
    for item in pending:
        if not item.get("resolved_user_id"):
            role_id = item.get("role_id")
            if role_id is None:
                raise ValueError("تعریف گردش کار ناقص است.")
            raise ValueError(
                format_missing_role_assignee_error(
                    db,
                    {
                        "label": item.get("label"),
                        "role_aliases": item.get("role_aliases") or [],
                        "order": item.get("order"),
                        "assignee_strategy": item.get("assignee_strategy"),
                    },
                    role_id,
                    exclude_user_ids=None,
                    submitter_id=submitter_id,
                )
            )


def preview_assignees(
    db: Session,
    ref_type: str,
    *,
    submitter_id: int | None,
) -> list[dict]:
    steps = get_steps_config(db, ref_type)
    preview: list[dict] = []
    for step in steps:
        role_id = resolve_role_id_for_step(db, step)
        if should_skip_missing_manager_step(db, step, submitter_id=submitter_id):
            preview.append(
                {
                    **serialize_step_for_api(step, role_id=role_id),
                    "resolved_user_id": None,
                    "resolved_user_name": None,
                    "duplicate_same_assignee": False,
                    "skipped_redundant": True,
                    "exclude_user_ids": [],
                    "skip_reason": "missing_manager",
                }
            )
            continue

        # بدون exclude تا همان نفر بتواند چند مرحلهٔ پشت‌سرهم را بگیرد
        resolved = resolve_step_assignee_user(
            db,
            step,
            role_id=role_id,
            submitter_id=submitter_id,
            exclude_user_ids=None,
        )
        resolved_id = resolved.id if resolved else None
        preview.append(
            {
                **serialize_step_for_api(step, role_id=role_id),
                "resolved_user_id": resolved_id,
                "resolved_user_name": _user_display(resolved),
                "duplicate_same_assignee": False,
                "skipped_redundant": False,
                "exclude_user_ids": [],
            }
        )
    return preview


def upsert_definition(
    db: Session,
    *,
    ref_type: str,
    name: str,
    steps: list,
    code: str | None = None,
) -> WorkflowDefinition:
    normalized = normalize_steps_config(steps)
    if not normalized:
        raise ValueError("steps must be a non-empty list")

    resolved_code = (code or ref_type).strip()
    row = get_definition_by_ref_type(db, ref_type)
    if row:
        row.name = name
        row.steps_config = normalized
        row.code = resolved_code
        db.commit()
        db.refresh(row)
        return row

    row = WorkflowDefinition(
        ref_type=ref_type,
        code=resolved_code,
        name=name,
        steps_config=normalized,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_definition(db: Session, ref_type: str) -> bool:
    row = get_definition_by_ref_type(db, ref_type)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
