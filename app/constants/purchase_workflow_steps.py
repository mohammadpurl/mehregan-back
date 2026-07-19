"""مراحل پیش‌فرض گردش‌کار یکپارچه خرید کالا."""

from __future__ import annotations

ACTION_APPROVAL = "approval"
ACTION_FILL_STOCK = "fill_stock"
ACTION_UPLOAD_PROFORMA = "upload_proforma"
ACTION_APPROVE_PROFORMA = "approve_proforma"
ACTION_UPLOAD_INVOICE = "upload_invoice"
ACTION_MARK_PAYMENT = "mark_payment"
ACTION_UPLOAD_BOL = "upload_bol"
ACTION_CONFIRM_RECEIPT = "confirm_receipt"
ACTION_CONFIRM_WAREHOUSE_SEPIDAR = "confirm_warehouse_sepidar"

PAYMENT_LOCATION_BANK = "bank"
PAYMENT_LOCATION_PETTY_CASH = "petty_cash"
PAYMENT_LOCATIONS = frozenset({PAYMENT_LOCATION_BANK, PAYMENT_LOCATION_PETTY_CASH})

PAYMENT_METHOD_CASH = "cash"
PAYMENT_METHOD_CHECK = "check"
PURCHASE_PAYMENT_METHODS = frozenset({PAYMENT_METHOD_CASH, PAYMENT_METHOD_CHECK})

PURCHASE_REQUEST_STEPS: list[dict] = [
    {
        "order": 1,
        "label": "ثبت موجودی انبار — سرپرست مالی",
        "role_aliases": ["finance_supervisor", "سرپرست مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_FILL_STOCK,
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
        "label": "ثبت و ارسال پیش‌فاکتور — مسئول خرید",
        "role_aliases": [
            "purchase_officer",
            "purchase_manager",
            "مسئول خرید",
            "مدیر خرید",
        ],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_UPLOAD_PROFORMA,
    },
    {
        "order": 4,
        "label": "تأیید پیش‌فاکتور و شرایط پرداخت — مدیرعامل",
        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_APPROVE_PROFORMA,
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
        "step_action": ACTION_UPLOAD_INVOICE,
    },
    {
        "order": 6,
        "label": "ثبت سپیدار و پرداخت — کارشناس مالی",
        "role_aliases": ["finance_officer", "کارشناس مالی", "مسئول پرداخت"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_MARK_PAYMENT,
    },
    {
        "order": 7,
        "label": "بارگذاری بارنامه — مسئول خرید",
        "role_aliases": [
            "purchase_officer",
            "purchase_manager",
            "مسئول خرید",
            "مدیر خرید",
        ],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_UPLOAD_BOL,
    },
    {
        "order": 8,
        "label": "تأیید دریافت کالا — مدیر پروژه",
        "role_aliases": ["project_manager", "مدیر پروژه"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_CONFIRM_RECEIPT,
    },
    {
        "order": 9,
        "label": "ورود به انبار و تأیید سپیدار — سرپرست مالی",
        "role_aliases": ["finance_supervisor", "سرپرست مالی"],
        "assignee_strategy": "role_pool",
        "step_action": ACTION_CONFIRM_WAREHOUSE_SEPIDAR,
    },
]
