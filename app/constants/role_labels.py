"""برچسب فارسی نقش‌ها (کلید پایدار: name انگلیسی در جدول roles)."""

from __future__ import annotations

ROLE_DISPLAY_NAMES: dict[str, str] = {
    "super-admin": "مدیر ارشد سیستم",
    "admin": "مدیر سیستم",
    "system_admin": "مدیر فنی",
    "ceo": "مدیرعامل",
    "managing_director": "مدیرعامل (قدیمی — ترجیحاً از ceo استفاده کنید)",
    "finance_manager": "مدیر مالی",
    "accountant": "حسابدار",
    "finance_officer": "کارشناس مالی",
    "finance_supervisor": "سرپرست مالی",
    "purchase_manager": "مدیر خرید",
    "purchase_officer": "مسئول خرید",
    "procurement_manager": "مدیر تدارکات",
    "warehouse_manager": "مدیر انبار",
    "warehouse": "انباردار",
    "manager": "مدیر",
    "project_manager": "مدیر پروژه",
    "employee": "کارمند",
}


def role_display_name(name: str | None, display_name: str | None = None) -> str:
    if display_name and str(display_name).strip():
        return str(display_name).strip()
    if not name:
        return "—"
    return ROLE_DISPLAY_NAMES.get(name.strip(), name)
