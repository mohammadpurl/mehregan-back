"""نمایش و snapshot حساب‌های بانکی."""

from __future__ import annotations

from typing import Protocol


class _BankFields(Protocol):
    label: str
    bank_name: str | None
    account_number: str | None
    sheba_number: str | None
    card_number: str | None


def bank_account_to_dict(row: _BankFields) -> dict:
    return {
        "label": row.label,
        "bankName": getattr(row, "bank_name", None),
        "accountNumber": row.account_number,
        "shebaNumber": row.sheba_number,
        "cardNumber": row.card_number,
        "displayLabel": format_bank_account_display(row),
    }


def format_bank_account_display(row: _BankFields) -> str:
    parts: list[str] = [row.label.strip()]
    if row.bank_name and row.bank_name.strip():
        parts.append(row.bank_name.strip())
    if row.sheba_number and row.sheba_number.strip():
        parts.append(f"شبا: {row.sheba_number.strip()}")
    elif row.account_number and row.account_number.strip():
        parts.append(f"حساب: {row.account_number.strip()}")
    if row.card_number and row.card_number.strip():
        parts.append(f"کارت: {row.card_number.strip()}")
    return " | ".join(parts)


def legacy_payer_format(label: str, account_number: str | None) -> str:
    num = (account_number or "").strip() or "-"
    return f"{label.strip()} | {num}"
