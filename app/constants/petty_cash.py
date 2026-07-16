"""وضعیت‌های درخواست تنخواه."""

# گردش تأیید
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"

# تسویه / ثبت جزئیات خرج
SETTLEMENT_NONE = "NONE"
SETTLEMENT_PENDING = "PENDING_SETTLEMENT"  # پس از تأیید؛ منتظر ثبت خرج
SETTLEMENT_PENDING_APPROVAL = "PENDING_SETTLEMENT_APPROVAL"  # خرج ثبت شد؛ در تأیید
SETTLEMENT_SETTLED = "SETTLED"

# گردش‌کار تأیید خرج (مدیر → مدیر مالی → مدیرعامل)
WORKFLOW_REF_PETTY_CASH_SETTLEMENT = "petty_cash_settlement"

PETTY_CASH_SETTLEMENT_STEPS = [
    {
        "order": 1,
        "label": "تأیید مدیر مستقیم — خرج تنخواه",
        "role_aliases": ["manager", "project_manager", "مدیر واحد", "مدیر مستقیم"],
        "assignee_strategy": "submitter_manager",
        "step_action": "approval",
    },
    {
        "order": 2,
        "label": "تأیید مدیر مالی — خرج تنخواه",
        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],
        "assignee_strategy": "role_pool",
        "step_action": "approval",
    },
    {
        "order": 3,
        "label": "تأیید مدیرعامل — خرج تنخواه",
        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
        "assignee_strategy": "role_pool",
        "step_action": "approval",
    },
]

EXPENSE_SOURCE_MANUAL = "manual"
EXPENSE_SOURCE_EXCEL = "excel"
