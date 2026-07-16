"""
تعمیر مراحل workflow که به‌اشتباه نقش super-admin دارند
ولی برچسب/منظورشان مدیرعامل است → به ceo تغییر می‌دهد.

  python scripts/repair_workflow_ceo_aliases.py
  python scripts/repair_workflow_ceo_aliases.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.workflow_definition import WorkflowDefinition
from app.services.workflow_step_config import normalize_steps_config

CEO_ALIASES = ["ceo", "managing_director", "مدیرعامل"]


def _looks_like_ceo_step(step: dict) -> bool:
    label = str(step.get("label") or "").replace(" ", "").replace("‌", "")
    aliases = {str(a).strip().lower() for a in (step.get("role_aliases") or [])}
    if aliases == {"super-admin"} or aliases == {"superadmin"}:
        return "مدیرعامل" in label or "مديرعامل" in label or "ceo" in label.lower()
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Apply changes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.query(WorkflowDefinition).all()
        changed = 0
        for row in rows:
            raw = row.steps_config
            if not isinstance(raw, list) or not raw:
                continue
            steps = normalize_steps_config(raw)
            dirty = False
            for step in steps:
                if not _looks_like_ceo_step(step):
                    continue
                print(
                    f"  {row.ref_type} order={step['order']} "
                    f"label={step.get('label')!r} "
                    f"aliases={step.get('role_aliases')} -> {CEO_ALIASES}"
                )
                step["role_aliases"] = list(CEO_ALIASES)
                dirty = True
            if dirty:
                changed += 1
                if args.yes:
                    row.steps_config = steps
        if args.yes and changed:
            db.commit()
            print(f"OK: repaired {changed} definition(s)")
        elif changed:
            print(f"Dry-run: {changed} definition(s) would change. Re-run with --yes")
        else:
            print("OK: nothing to repair")
    finally:
        db.close()


if __name__ == "__main__":
    main()
