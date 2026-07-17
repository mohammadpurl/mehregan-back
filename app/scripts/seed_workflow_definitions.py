"""
Seed workflow_definitions from built-in defaults (former in-code matrix).
Run: python -m app.scripts.seed_workflow_definitions
     python -m app.scripts.seed_workflow_definitions --force
"""

import argparse

from app.core.database import SessionLocal
from app.services.workflow_definition_service import DEFAULT_ROLE_STEPS, ensure_definition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing definitions (wipes admin UI edits)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        for ref_type, steps in DEFAULT_ROLE_STEPS.items():
            row = ensure_definition(
                db,
                ref_type=ref_type,
                name=f"Default workflow for {ref_type}",
                steps=steps,
                code=ref_type,
                force=args.force,
            )
            if row:
                print(f"Seeded workflow definition: {ref_type}")
            else:
                print(f"SKIP: {ref_type} already exists")
    finally:
        db.close()


if __name__ == "__main__":
    main()
