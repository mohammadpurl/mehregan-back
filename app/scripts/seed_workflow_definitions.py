"""
Seed workflow_definitions from built-in defaults (former in-code matrix).
Run: python -m app.scripts.seed_workflow_definitions
"""

from app.core.database import SessionLocal
from app.services.workflow_definition_service import DEFAULT_ROLE_STEPS, upsert_definition


def main():
    db = SessionLocal()
    try:
        for ref_type, steps in DEFAULT_ROLE_STEPS.items():
            upsert_definition(
                db,
                ref_type=ref_type,
                name=f"Default workflow for {ref_type}",
                steps=steps,
                code=ref_type,
            )
            print(f"Seeded workflow definition: {ref_type}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
