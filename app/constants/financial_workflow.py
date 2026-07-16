"""ثابت‌ها و مراحل پیش‌فرض روال یکسان تأیید مالی + سپیدار."""

from __future__ import annotations

WORKFLOW_REF_PAYMENT_REQUEST = "payment_request"
WORKFLOW_REF_PAYMENT_ORDER = "payment_order"
WORKFLOW_REF_PETTY_CASH = "petty_cash"
WORKFLOW_REF_FINANCIAL_DOCUMENT = "financial_document"

FINANCIAL_WORKFLOW_REF_TYPES = frozenset(
    {
        WORKFLOW_REF_PAYMENT_REQUEST,
        WORKFLOW_REF_PAYMENT_ORDER,
        WORKFLOW_REF_PETTY_CASH,
        WORKFLOW_REF_FINANCIAL_DOCUMENT,
    }
)

ACTION_APPROVAL = "approval"
ACTION_MARK_PAYMENT = "mark_payment"
ACTION_CONFIRM_SEPIDAR = "confirm_sepidar"
# سازگاری با تعریف‌های قدیمی دستور پرداخت
ACTION_FINAL_PAYMENT_APPROVAL = "final_payment_approval"

CONFIRM_SEPIDAR_ACTIONS = frozenset(
    {ACTION_CONFIRM_SEPIDAR, ACTION_FINAL_PAYMENT_APPROVAL}
)

# روال یکسان: مدیر مستقیم → مدیر مالی → مدیرعامل → کارشناس مالی → سرپرست مالی
UNIFIED_FINANCIAL_STEPS: list[dict] = [
    {
        "order": 1,
        "label": "تأیید مدیر مستقیم",
        "role_aliases": ["manager", "project_manager", "مدیر واحد", "مدیر مستقیم"],
        "assignee_strategy": "submitter_manager",
        "step_action": ACTION_APPROVAL,
    },
    {
        "order": 2,
        "label": "تأیید مدیر مالی",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_APPROVAL,
    },
    {
        "order": 3,
        "label": "تأیید مدیرعامل",
        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_APPROVAL,
    },
    {
        "order": 4,
        "label": "ثبت در سپیدار — کارشناس مالی",
        "role_aliases": [
            "finance_officer",
            "کارشناس مالی",
            "مسئول پرداخت",
        ],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_MARK_PAYMENT,
    },
    {
        "order": 5,
        "label": "تأیید ثبت سپیدار — سرپرست مالی",
        "role_aliases": ["finance_supervisor", "سرپرست مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_CONFIRM_SEPIDAR,
    },
]
