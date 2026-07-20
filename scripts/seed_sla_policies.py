"""
هم‌ترازسازی سیاست‌های SLA با تعریف‌های گردش‌کار + backfill مهلت مراحل باز.

Run:
  python scripts/seed_sla_policies.py
  python scripts/seed_sla_policies.py --backfill
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.services.sla import backfill_open_sla_records
from app.services.sla_policy_service import (
    DEFAULT_SLA_MAX_MINUTES,
    sync_sla_policies_from_definitions,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="برای مراحل pending بدون مهلت، sla_record بساز",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        created = sync_sla_policies_from_definitions(
            db, max_minutes=DEFAULT_SLA_MAX_MINUTES, commit=True
        )
        print(f"SLA policies synced: {created} new row(s)")
        if args.backfill:
            n = backfill_open_sla_records(db)
            print(f"SLA backfill: {n} record(s) created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
