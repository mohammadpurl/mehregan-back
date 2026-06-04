"""
Seed default SLA policies for all workflow types.
Run: python scripts/seed_sla_policies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.sla_policy import SlaPolicy

# ref_type -> number of steps (from workflow_definition_service defaults)
WORKFLOW_STEP_COUNTS: dict[str, int] = {
    "workflow_form": 1,
    "payment_request": 2,
    "payment_order": 5,
    "financial_document": 2,
    "warehouse_form": 3,
    "purchase_request": 6,
    "request": 2,
    "procurement_proforma": 1,
    "petty_cash": 1,
    "mission_request": 2,
}

DEFAULT_MAX_MINUTES = 24 * 60  # 24 hours per step


def _ceo_role_id(db) -> int | None:
    row = (
        db.query(Role)
        .filter(func.lower(Role.name).in_(("ceo", "managing_director", "مدیرعامل")))
        .first()
    )
    return row.id if row else None


def main() -> None:
    db = SessionLocal()
    try:
        ceo_role_id = _ceo_role_id(db)
        created = 0
        for ref_type, step_count in WORKFLOW_STEP_COUNTS.items():
            for step_order in range(1, step_count + 1):
                exists = (
                    db.query(SlaPolicy)
                    .filter(
                        SlaPolicy.ref_type == ref_type,
                        SlaPolicy.step_order == step_order,
                    )
                    .first()
                )
                if exists:
                    continue
                db.add(
                    SlaPolicy(
                        ref_type=ref_type,
                        step_order=step_order,
                        max_minutes=DEFAULT_MAX_MINUTES,
                        escalate_to_role_id=ceo_role_id,
                        is_active=True,
                    )
                )
                created += 1
        db.commit()
        print(f"SLA policies seeded: {created} new row(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
