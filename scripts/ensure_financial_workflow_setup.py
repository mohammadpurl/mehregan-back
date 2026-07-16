"""
اعمال روال یکسان ۵مرحله‌ای مالی + نقش‌های کارشناس/سرپرست مالی.

  python scripts/ensure_financial_workflow_setup.py
  python scripts/ensure_financial_workflow_setup.py --ensure-roles
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def upsert_all(db) -> None:
    unified = list(UNIFIED_FINANCIAL_STEPS)
    settlement = list(PETTY_CASH_SETTLEMENT_STEPS)
    for ref_type, name in REF_DEFS:
        steps = settlement if ref_type == WORKFLOW_REF_PETTY_CASH_SETTLEMENT else unified
        upsert_definition(db, ref_type=ref_type, name=name, steps=steps)
        print(f"OK: workflow_definitions.{ref_type}")
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ensure-roles",
        action="store_true",
        help="ایجاد نقش‌های finance_officer و finance_supervisor در صورت نبود",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.ensure_roles:
            ensure_roles(db)
        upsert_all(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
