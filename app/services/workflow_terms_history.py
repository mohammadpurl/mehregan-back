"""Snapshot و diff شرایط مالی هنگام تأیید workflow."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.constants.payment_order import WORKFLOW_REF_PAYMENT_ORDER
from app.models.workflow_instance import WorkflowInstance

_TRACKED_PAYMENT_FIELDS = (
    "amount",
    "payment_date",
    "installment_count",
    "first_installment_date",
    "settlement_date",
    "payer_company_account_id",
    "payer_account",
    "payment_method",
)

_FIELD_API_KEYS = {
    "amount": "amount",
    "payment_date": "paymentDate",
    "requested_date": "paymentDate",
    "document_date": "paymentDate",
    "installment_count": "installmentCount",
    "first_installment_date": "firstInstallmentDate",
    "settlement_date": "settlementDate",
    "payer_company_account_id": "payerCompanyAccountId",
    "payer_account": "payerAccount",
    "payment_method": "paymentMethod",
}

_FIELD_LABELS = {
    "amount": "مبلغ",
    "payment_date": "تاریخ پرداخت",
    "requested_date": "تاریخ پرداخت",
    "document_date": "تاریخ سند",
    "installment_count": "تعداد اقساط",
    "first_installment_date": "تاریخ شروع قسط اول",
    "settlement_date": "تاریخ تسویه",
    "payer_company_account_id": "حساب مبدأ شرکت",
    "payer_account": "حساب مبدأ",
    "payment_method": "روش پرداخت",
}


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value
    return str(value)


def _values_equal(old: Any, new: Any) -> bool:
    if old is None and new is None:
        return True
    if old is None or new is None:
        return False
    if isinstance(old, (int, float, Decimal)) and isinstance(new, (int, float, Decimal)):
        return float(old) == float(new)
    return old == new


def snapshot_financial_terms(
    db: Session, inst: WorkflowInstance | None
) -> dict[str, Any] | None:
    """وضعیت فعلی فیلدهای قابل‌تغییر تأییدکننده را برمی‌گرداند."""
    if not inst:
        return None

    if inst.ref_type in ("payment_request", WORKFLOW_REF_PAYMENT_ORDER):
        from app.models.payment_request import PaymentRequest

        pr = db.get(PaymentRequest, inst.ref_id)
        if not pr:
            return None
        return {
            "entity": "payment_request",
            "entityId": int(pr.id),
            "fields": {
                key: _serialize_value(getattr(pr, key, None))
                for key in _TRACKED_PAYMENT_FIELDS
            },
        }

    if inst.ref_type == "petty_cash":
        from app.models.petty_cash_request import PettyCashRequest

        row = db.get(PettyCashRequest, inst.ref_id)
        if not row:
            return None
        return {
            "entity": "petty_cash",
            "entityId": int(row.id),
            "fields": {
                "amount": _serialize_value(row.amount),
                "requested_date": _serialize_value(row.requested_date),
                "payer_company_account_id": _serialize_value(
                    row.payer_company_account_id
                ),
            },
        }

    if inst.ref_type == "financial_document":
        from app.models.financial_document import FinancialDocument

        row = db.get(FinancialDocument, inst.ref_id)
        if not row:
            return None
        return {
            "entity": "financial_document",
            "entityId": int(row.id),
            "fields": {
                "amount": _serialize_value(row.amount),
                "document_date": _serialize_value(row.document_date),
            },
        }

    return None


def diff_financial_terms(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """لیست تغییرات فیلدها برای ذخیره در workflow_approvals / audit."""
    if not before or not after:
        return []
    before_fields = before.get("fields") or {}
    after_fields = after.get("fields") or {}
    keys = sorted(set(before_fields) | set(after_fields))
    changes: list[dict[str, Any]] = []
    for key in keys:
        old_v = before_fields.get(key)
        new_v = after_fields.get(key)
        if _values_equal(old_v, new_v):
            continue
        changes.append(
            {
                "field": _FIELD_API_KEYS.get(key, key),
                "sourceField": key,
                "label": _FIELD_LABELS.get(key, key),
                "oldValue": old_v,
                "newValue": new_v,
            }
        )
    return changes


def serialize_field_changes_for_api(
    field_changes: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    if not field_changes:
        return None
    if isinstance(field_changes, dict):
        # سازگاری با شکل ذخیره‌شدهٔ احتمالی {changes: [...], entity: ...}
        items = field_changes.get("changes")
        if not isinstance(items, list):
            return None
        field_changes = items
    out: list[dict[str, Any]] = []
    for item in field_changes:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "field": item.get("field"),
                "label": item.get("label"),
                "oldValue": item.get("oldValue"),
                "newValue": item.get("newValue"),
            }
        )
    return out or None
