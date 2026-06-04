"""
همگام‌سازی وضعیت درخواست‌های خرید با گردش‌کار تأییدشده.

  python scripts/repair_purchase_request_status.py
  python scripts/repair_purchase_request_status.py --id 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.procurement import REQUEST_TYPE_PURCHASE, STATUS_PENDING
from app.core.database import SessionLocal
from app.models.request import Request
from app.services.procurement.purchase_request_service import (
    sync_purchase_request_status_from_workflow,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="فقط یک درخواست خاص")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Request).filter(Request.type == REQUEST_TYPE_PURCHASE)
        if args.id:
            query = query.filter(Request.id == args.id)
        else:
            query = query.filter(Request.status == STATUS_PENDING)

        rows = query.all()
        fixed = 0
        for req in rows:
            if sync_purchase_request_status_from_workflow(db, req.id):
                db.refresh(req)
                print(f"OK request #{req.id} -> status={req.status}")
                fixed += 1
        print(f"Done. updated={fixed} scanned={len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
