"""سیاست نقش‌ها: نقش‌های تک‌نفره و قوانین مشترک."""

from __future__ import annotations

# نقش‌هایی که در seed و migration به is_singleton=True تنظیم می‌شوند
DEFAULT_SINGLETON_ROLE_NAMES: frozenset[str] = frozenset(
    {
        "ceo",
        "finance_manager",
    }
)
