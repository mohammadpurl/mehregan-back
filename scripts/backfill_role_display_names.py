"""
پر کردن display_name خالی نقش‌ها از role_labels.py

  python scripts/backfill_role_display_names.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants.role_labels import ROLE_DISPLAY_NAMES, role_display_name
from app.core.database import SessionLocal
from app.models.role import Role


def main() -> None:
    db = SessionLocal()
    updated = 0
    try:
        for role in db.query(Role).order_by(Role.id):
            label = role_display_name(role.name, role.display_name)
            if not role.display_name or role.display_name.strip() != label:
                role.display_name = label
                updated += 1
                print(f"  {role.name} -> {label}")
        db.commit()
        print(f"Updated {updated} role(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
