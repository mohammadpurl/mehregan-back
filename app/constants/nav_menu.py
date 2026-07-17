"""
تعریف منوی ERP — هر آیتم با permission موردنیاز (خالی = همه کاربران واردشده).

فرانت می‌تواند GET /auth/menus را بخواند یا همین کدها را در navItems تکرار کند.
"""

from __future__ import annotations

from typing import Any

NavItemDef = dict[str, Any]

NAV_MENU: list[NavItemDef] = [
    {
        "key": "dashboard",
        "href": "/dashboard",
        "label": "داشبورد",
        "required_permissions": ["dashboard.read"],
    },
    {
        "key": "profile",
        "href": "/dashboard/profile",
        "label": "پروفایل من",
        "required_permissions": [],
    },
    {
        "key": "payment-request",
        "href": "/dashboard/payment-request",
        "label": "درخواست‌های مالی",
        "required_permissions": ["payment.create"],
    },
    {
        "key": "petty-cash",
        "label": "تنخواه",
        "children": [
            {
                "key": "petty-cash-request",
                "href": "/dashboard/petty-cash",
                "label": "درخواست تنخواه",
                "required_permissions": ["payment.create"],
            },
            {
                "key": "petty-cash-settlement",
                "href": "/dashboard/petty-cash/settlement",
                "label": "ثبت خرج تنخواه",
                "required_permissions": ["payment.create"],
            },
            {
                "key": "petty-cash-ledger",
                "href": "/dashboard/petty-cash/ledger",
                "label": "دفتر تنخواه (گزارش)",
                "required_permissions": ["payment.approve", "payment.create"],
            },
        ],
    },
    {
        "key": "mission-request",
        "href": "/dashboard/mission-requests",
        "label": "درخواست ماموریت",
        "required_permissions": ["payment.create"],
    },
    {
        "key": "workflow",
        "label": "گردش کار",
        "children": [
            {
                "key": "workflow-inbox",
                "href": "/dashboard/workflow/inbox",
                "label": "کارهای من (Inbox)",
                "required_permissions": ["workflow.inbox.read"],
            },
            {
                "key": "ad-hoc-tasks",
                "href": "/dashboard/ad-hoc-tasks",
                "label": "کارهای پیش‌بینی‌نشده",
                "required_permissions": [],
            },
            {
                "key": "workflow-tracking",
                "href": "/dashboard/workflow/tracking",
                "label": "پیگیری گردش کار",
                "required_permissions": ["workflow.tracking.read"],
            },
            {
                "key": "reports-sla",
                "href": "/dashboard/reports/sla",
                "label": "گزارش SLA",
                "required_permissions": ["workflow.tracking.read"],
            },
            {
                "key": "reports-financial",
                "href": "/dashboard/reports/financial",
                "label": "گزارش مالی اجرایی",
                "required_permissions": ["payment.approve", "workflow.all.read", "admin.manage"],
            },
            {
                "key": "reports-warehouse",
                "href": "/dashboard/reports/warehouse",
                "label": "گزارش روزانه انبار",
                "required_permissions": ["inventory.read", "procurement.read"],
            },
        ],
    },
    {
        "key": "procurement",
        "label": "تدارکات",
        "children": [
            {
                "key": "procurement-requests",
                "href": "/dashboard/procurement/requests",
                "label": "درخواست‌ها (PR)",
                "required_permissions": ["procurement.read"],
            },
            {
                "key": "procurement-orders",
                "href": "/dashboard/procurement/orders",
                "label": "سفارش‌های خرید (PO)",
                "required_permissions": ["procurement.read"],
            },
            {
                "key": "procurement-grn",
                "href": "/dashboard/procurement/grn",
                "label": "دریافت کالا (GRN)",
                "required_permissions": ["procurement.read"],
            },
        ],
    },
    {
        "key": "inventory",
        "label": "انبار",
        "children": [
            {
                "key": "inventory-stock",
                "href": "/dashboard/inventory/stock",
                "label": "موجودی انبار",
                "required_permissions": ["inventory.read"],
            },
            {
                "key": "inventory-transactions",
                "href": "/dashboard/inventory/transactions",
                "label": "تراکنش‌ها",
                "required_permissions": ["inventory.transfer"],
            },
        ],
    },
    {
        "key": "master",
        "label": "اطلاعات پایه",
        "children": [
            {
                "key": "master-items",
                "href": "/dashboard/master/items",
                "label": "کالاها",
                "required_permissions": ["item.read", "item.*"],
            },
            {
                "key": "master-categories",
                "href": "/dashboard/master/categories",
                "label": "گروه کالا",
                "required_permissions": ["masterdata.manage"],
            },
            {
                "key": "master-warehouses",
                "href": "/dashboard/master/warehouses",
                "label": "انبارها",
                "required_permissions": ["masterdata.manage"],
            },
            {
                "key": "master-suppliers",
                "href": "/dashboard/master/suppliers",
                "label": "تامین‌کنندگان",
                "required_permissions": ["masterdata.manage"],
            },
        ],
    },
    {
        "key": "admin",
        "label": "مدیریت",
        "required_permissions": ["admin.manage"],
        "children": [
            {
                "key": "admin-users",
                "href": "/dashboard/admin/users",
                "label": "کاربران",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-departments",
                "href": "/dashboard/admin/departments/tree",
                "label": "واحدهای سازمانی",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-roles",
                "href": "/dashboard/admin/roles",
                "label": "نقش‌ها",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-permissions",
                "href": "/dashboard/admin/permissions",
                "label": "مجوزها",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-assignment-rules",
                "href": "/dashboard/admin/assignment-rules",
                "label": "مجوزهای نقش",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-workflow-definitions",
                "href": "/dashboard/admin/workflow-definitions",
                "label": "تعریف workflow",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-audit",
                "href": "/dashboard/admin/audit",
                "label": "مرکز ممیزی",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-counterparties",
                "href": "/dashboard/admin/counterparties",
                "label": "طرف‌حساب‌ها",
                "required_permissions": ["admin.manage"],
            },
            {
                "key": "admin-company-bank-accounts",
                "href": "/dashboard/admin/company-bank-accounts",
                "label": "حساب‌های بانکی شرکت",
                "required_permissions": ["admin.manage"],
            },
        ],
    },
]
