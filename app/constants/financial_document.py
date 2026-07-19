"""ثابت‌های اسناد مالی."""

from app.constants.financial_workflow import (
    ACTION_APPROVAL,
    ACTION_CONFIRM_SEPIDAR,
    ACTION_MARK_PAYMENT,
)

WORKFLOW_REF_FINANCIAL_DOCUMENT = "financial_document"

DOCUMENT_TYPE_CHECK = "check"
DOCUMENT_TYPE_OTHER = "other"

DOCUMENT_TYPES = frozenset({DOCUMENT_TYPE_CHECK, DOCUMENT_TYPE_OTHER})

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

# کارشناس مالی (عکس + ثبت سپیدار) → سرپرست → مدیر مالی → رویت/تأیید نهایی مدیر مالی
FINANCIAL_DOCUMENT_STEPS: list[dict] = [
    {
        "order": 1,
        "label": "ثبت تصویر و ثبت در سپیدار — کارشناس مالی",
        "role_aliases": [
            "finance_officer",
            "کارشناس مالی",
            "مسئول پرداخت",
        ],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_MARK_PAYMENT,
    },
    {
        "order": 2,
        "label": "تأیید ثبت سپیدار — سرپرست مالی",
        "role_aliases": ["finance_supervisor", "سرپرست مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_CONFIRM_SEPIDAR,
    },
    {
        "order": 3,
        "label": "تأیید مدیر مالی",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_APPROVAL,
    },
    {
        "order": 4,
        "label": "رویت و تأیید نهایی مدیر مالی",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_APPROVAL,
        "allow_auto_skip": False,
    },
]
