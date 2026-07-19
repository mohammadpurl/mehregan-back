"""
راه‌اندازی نقش‌های مالی و (اختیاری) بازنشانی تعریف‌های workflow مالی.

  # فقط نقش‌ها — تعریف‌های ذخیره‌شده در ادمین را دست نمی‌زند
  python scripts/ensure_financial_workflow_setup.py --ensure-roles

  # فقط تعریف‌های ناموجود را بساز (موجودها را بازنویسی نکن)
  python scripts/ensure_financial_workflow_setup.py --seed-missing-definitions

  # بازنشانی اجباری تعریف‌ها به الگوی ثابت UNIFIED_FINANCIAL_STEPS
  # (تغییرات ادمین را پاک می‌کند — فقط وقتی عمداً می‌خواهید)
  python scripts/ensure_financial_workflow_setup.py --reset-definitions
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.financial_document import FINANCIAL_DOCUMENT_STEPS
from app.constants.financial_workflow import (
    UNIFIED_FINANCIAL_STEPS,
    WORKFLOW_REF_FINANCIAL_DOCUMENT,
    WORKFLOW_REF_PAYMENT_ORDER,
    WORKFLOW_REF_PAYMENT_REQUEST,
    WORKFLOW_REF_PETTY_CASH,
)
from app.constants.petty_cash import (
    PETTY_CASH_SETTLEMENT_STEPS,
    WORKFLOW_REF_PETTY_CASH_SETTLEMENT,
)
from app.constants.role_labels import ROLE_DISPLAY_NAMES
from app.core.database import SessionLocal
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.permission import Permission
from app.models.workflow_definition import WorkflowDefinition
from app.services.workflow_definition_service import upsert_definition

REF_DEFS = [
    (WORKFLOW_REF_PAYMENT_REQUEST, "درخواست پرداخت / وام / مساعده"),
    (WORKFLOW_REF_PAYMENT_ORDER, "دستور پرداخت"),
    (WORKFLOW_REF_PETTY_CASH, "درخواست تنخواه"),
    (WORKFLOW_REF_FINANCIAL_DOCUMENT, "اسناد مالی"),
    (WORKFLOW_REF_PETTY_CASH_SETTLEMENT, "تأیید خرج تنخواه"),
]

NEW_ROLE_PERMS = {
    "finance_officer": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "payment.create",
        "payment.approve",
    ],
    "finance_supervisor": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "payment.approve",
    ],
}


def ensure_roles(db) -> None:
    for slug, codes in NEW_ROLE_PERMS.items():
        role = db.query(Role).filter(Role.name == slug).first()
        if not role:
            role = Role(
                name=slug,
                display_name=ROLE_DISPLAY_NAMES.get(slug, slug),
            )
            db.add(role)
            db.flush()
            print(f"Created role {slug}")
        else:
            print(f"OK: role {slug} exists")

        for code in codes:
            perm = db.query(Permission).filter(Permission.code == code).first()
            if not perm:
                print(f"WARN: permission {code} missing — skip bind")
                continue
            existing = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
                .first()
            )
            if not existing:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                print(f"  + {slug} ← {code}")
    db.commit()


def _default_steps_for(ref_type: str) -> list:
    if ref_type == WORKFLOW_REF_PETTY_CASH_SETTLEMENT:
        return list(PETTY_CASH_SETTLEMENT_STEPS)
    if ref_type == WORKFLOW_REF_FINANCIAL_DOCUMENT:
        return list(FINANCIAL_DOCUMENT_STEPS)
    return list(UNIFIED_FINANCIAL_STEPS)


def upsert_missing_only(db) -> None:
    """فقط اگر تعریف وجود ندارد، الگوی پیش‌فرض را می‌نویسد — تعریف ادمین را بازنویسی نمی‌کند."""
    for ref_type, name in REF_DEFS:
        exists = (
            db.query(WorkflowDefinition.id)
            .filter(WorkflowDefinition.ref_type == ref_type)
            .first()
        )
        if exists:
            print(
                f"SKIP: workflow_definitions.{ref_type} already exists "
                "(admin edits preserved)"
            )
            continue
        upsert_definition(
            db, ref_type=ref_type, name=name, steps=_default_steps_for(ref_type)
        )
        print(f"CREATED: workflow_definitions.{ref_type}")


def reset_all_definitions(db) -> None:
    """بازنویسی اجباری تعریف‌های مالی — تغییرات ادمین پاک می‌شود."""
    for ref_type, name in REF_DEFS:
        upsert_definition(
            db, ref_type=ref_type, name=name, steps=_default_steps_for(ref_type)
        )
        print(f"RESET: workflow_definitions.{ref_type}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Financial workflow roles / definitions setup"
    )
    parser.add_argument(
        "--ensure-roles",
        action="store_true",
        help="ایجاد نقش‌های finance_officer و finance_supervisor در صورت نبود",
    )
    parser.add_argument(
        "--reset-definitions",
        action="store_true",
        help="بازنویسی اجباری تعریف‌های مالی (تغییرات UI ادمین را پاک می‌کند)",
    )
    parser.add_argument(
        "--seed-missing-definitions",
        action="store_true",
        help="فقط تعریف‌های ناموجود را با الگوی پیش‌فرض بساز (موجودها را دست نزن)",
    )
    args = parser.parse_args()

    if not (
        args.ensure_roles or args.reset_definitions or args.seed_missing_definitions
    ):
        parser.error(
            "حداقل یکی از --ensure-roles / --seed-missing-definitions / --reset-definitions لازم است"
        )

    db = SessionLocal()
    try:
        if args.ensure_roles:
            ensure_roles(db)
        if args.reset_definitions:
            reset_all_definitions(db)
        elif args.seed_missing_definitions:
            upsert_missing_only(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
