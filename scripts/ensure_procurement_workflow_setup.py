"""

تعریف گردش‌کار درخواست خرید کالا (یکپارچه) و legacy در دیتابیس.



  python scripts/ensure_procurement_workflow_setup.py

  python scripts/ensure_procurement_workflow_setup.py --repair-instances

"""



from __future__ import annotations



import argparse

import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:

    sys.path.insert(0, str(ROOT))



from app.core.database import SessionLocal

from app.constants.procurement import (

    WORKFLOW_REF_PROFORMA,

    WORKFLOW_REF_PURCHASE,

    WORKFLOW_REF_REQUEST,

)

from app.models.request import Request
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.workflow_instance import WorkflowInstance

from app.models.workflow_step import WorkflowStep

from app.services.workflow_definition_service import get_steps_config, upsert_definition

from app.services.workflow_step_config import (

    resolve_role_id_for_step,

    resolve_step_assignee_user,

)



# گردش‌کار یکپارچه — همه مراحل در یک instance

PURCHASE_REQUEST_STEPS = [

    {

        "order": 1,

        "label": "تأیید مدیر مالی",

        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],

        "assignee_strategy": "role_pool",

        "step_action": "approval",

    },

    {

        "order": 2,

        "label": "تأیید مدیرعامل — درخواست",

        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],

        "assignee_strategy": "role_pool",

        "step_action": "approval",

    },

    {

        "order": 3,

        "label": "ثبت و ارسال پیش‌فاکتور — مسئول خرید",

        "role_aliases": ["purchase_officer", "purchase_manager", "مسئول خرید", "مدیر خرید"],

        "assignee_strategy": "role_pool",

        "step_action": "upload_proforma",

    },

    {

        "order": 4,

        "label": "تأیید پیش‌فاکتور و روش پرداخت — مدیرعامل",

        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],

        "assignee_strategy": "role_pool",

        "step_action": "approve_proforma",

    },

    {

        "order": 5,

        "label": "بارگذاری فاکتور — مسئول خرید",

        "role_aliases": ["purchase_officer", "purchase_manager", "مسئول خرید", "مدیر خرید"],

        "assignee_strategy": "role_pool",

        "step_action": "upload_invoice",

    },

    {

        "order": 6,

        "label": "تأیید پرداخت فاکتور — مدیر مالی",

        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],

        "assignee_strategy": "role_pool",

        "step_action": "confirm_payment",

    },

]



# legacy — درخواست‌های قدیمی

REQUEST_STEPS = [

    {

        "order": 1,

        "label": "تأیید مدیر مالی",

        "role_aliases": ["finance_manager", "accountant", "مدیر مالی"],

        "assignee_strategy": "role_pool",

    },

    {

        "order": 2,

        "label": "تأیید مدیرعامل",

        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],

        "assignee_strategy": "role_pool",

    },

]



PROFORMA_STEPS = [

    {

        "order": 1,

        "label": "تأیید پیش‌فاکتور و روش پرداخت — مدیرعامل",

        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],

        "assignee_strategy": "role_pool",

        "step_action": "approve_proforma",

    },

]

CEO_ALIASES = ["ceo", "managing_director", "مدیرعامل"]


def sync_ceo_aliases_in_definitions(db) -> int:
    from app.models.workflow_definition import WorkflowDefinition

    updated = 0
    for row in db.query(WorkflowDefinition).all():
        steps = row.steps_config
        if not isinstance(steps, list):
            continue
        changed = False
        new_steps = []
        for step in steps:
            if not isinstance(step, dict):
                new_steps.append(step)
                continue
            aliases = step.get("role_aliases") or step.get("roleAliases") or []
            if not any(str(a).lower() in ("ceo", "managing_director", "مدیرعامل") for a in aliases):
                new_steps.append(step)
                continue
            merged = list(dict.fromkeys([*CEO_ALIASES, *[str(a) for a in aliases]]))
            if merged != aliases:
                changed = True
            new_steps.append({**step, "role_aliases": merged})
        if changed:
            row.steps_config = new_steps
            updated += 1
    if updated:
        db.commit()
    return updated


def merge_managing_director_into_ceo(db) -> int:
    ceo = db.query(Role).filter(Role.name == "ceo").first()
    md = db.query(Role).filter(Role.name == "managing_director").first()
    if not ceo or not md:
        return 0
    fixed = 0
    active_md = (
        db.query(UserRole)
        .filter(UserRole.role_id == md.id, UserRole.is_active == True)  # noqa: E712
        .all()
    )
    for ur in active_md:
        existing = (
            db.query(UserRole)
            .filter(UserRole.user_id == ur.user_id, UserRole.role_id == ceo.id)
            .first()
        )
        if existing:
            if not existing.is_active:
                existing.is_active = True
                fixed += 1
        else:
            db.add(UserRole(user_id=ur.user_id, role_id=ceo.id, is_active=True))
            fixed += 1
    if fixed:
        db.commit()
    return fixed


def repair_pending_instances(db, ref_type: str) -> int:

    """نقش و تأییدکنندهٔ مراحل pending را با تعریف فعلی هم‌راستا می‌کند."""

    fixed = 0

    steps_config = get_steps_config(db, ref_type)

    if not steps_config:

        return 0



    instances = (

        db.query(WorkflowInstance)

        .filter(

            WorkflowInstance.ref_type == ref_type,

            WorkflowInstance.status == "pending",

        )

        .all()

    )



    for inst in instances:

        req = db.get(Request, inst.ref_id)

        submitter_id = req.requester_id if req else None

        steps = (

            db.query(WorkflowStep)

            .filter_by(instance_id=inst.id)

            .order_by(WorkflowStep.order)

            .all()

        )

        prev_assignee: int | None = None

        for step in steps:

            if step.status != "pending":

                if step.assigned_user_id:

                    prev_assignee = step.assigned_user_id

                continue

            idx = step.order - 1

            if idx < 0 or idx >= len(steps_config):

                continue

            cfg = steps_config[idx]

            role_id = resolve_role_id_for_step(db, cfg)

            exclude = [prev_assignee] if prev_assignee is not None else []

            assignee = resolve_step_assignee_user(

                db,

                cfg,

                role_id=role_id,

                submitter_id=submitter_id,

                exclude_user_ids=exclude,

            )

            if not assignee:

                continue

            changed = False

            if step.role_id != role_id:

                step.role_id = role_id

                changed = True

            if step.assigned_user_id != assignee.id:

                step.assigned_user_id = assignee.id

                changed = True

            if changed:

                fixed += 1

                print(

                    f"instance {inst.id} ({ref_type}) step {step.order}: "

                    f"role={role_id} assignee={assignee.id}"

                )

            prev_assignee = assignee.id



    if fixed:

        db.commit()

    return fixed





def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(

        "--repair-instances",

        action="store_true",

        help="هم‌راستاسازی مراحل pending با تعریف فعلی",

    )

    args = parser.parse_args()



    db = SessionLocal()

    try:

        upsert_definition(

            db,

            ref_type=WORKFLOW_REF_PURCHASE,

            name="درخواست خرید کالا (یکپارچه)",

            steps=PURCHASE_REQUEST_STEPS,

        )

        print("OK: workflow definition 'purchase_request' (unified)")

        upsert_definition(

            db,

            ref_type=WORKFLOW_REF_REQUEST,

            name="درخواست خرید (legacy)",

            steps=REQUEST_STEPS,

        )

        print("OK: workflow definition 'request' (legacy)")

        upsert_definition(

            db,

            ref_type=WORKFLOW_REF_PROFORMA,

            name="پیش‌فاکتور خرید (legacy)",

            steps=PROFORMA_STEPS,

        )

        print("OK: workflow definition 'procurement_proforma' (legacy)")

        n_alias = sync_ceo_aliases_in_definitions(db)
        if n_alias:
            print(f"OK: synced CEO aliases in {n_alias} workflow definition(s)")
        n_ceo = merge_managing_director_into_ceo(db)
        if n_ceo:
            print(f"OK: activated ceo role for {n_ceo} user(s) (from managing_director)")

        if args.repair_instances:

            n0 = repair_pending_instances(db, WORKFLOW_REF_PURCHASE)

            n1 = repair_pending_instances(db, WORKFLOW_REF_REQUEST)

            n2 = repair_pending_instances(db, WORKFLOW_REF_PROFORMA)

            print(f"Repaired {n0 + n1 + n2} step assignment(s)")

    finally:

        db.close()





if __name__ == "__main__":

    main()


