"""
خروجی کاربران، نقش‌ها، مجوزها و تنظیمات workflow از دیتابیس فعلی به JSON.

خروجی شامل:
  - roles, permissions, role_permissions
  - departments, users, user_roles
  - workflow_definitions, assignment_rules, sla_policies

اجرا روی ماشین محلی (همان دیتابیس منبع):
  python scripts/export_rbac_workflow.py
  python scripts/export_rbac_workflow.py -o dumps/rbac_workflow.json

اجرا داخل کانتینر backend (اگر منبع همان DB داکر است):
  docker compose exec backend python scripts/export_rbac_workflow.py -o /tmp/rbac_workflow.json
  docker compose cp mehregan-backend:/tmp/rbac_workflow.json ./dumps/rbac_workflow.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.models.assignment_rule import AssignmentRule
from app.models.department import Department
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.sla_policy import SlaPolicy
from app.models.user import User
from app.models.user_role import UserRole
from app.models.workflow_definition import WorkflowDefinition


def _dt(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def export_all(db) -> dict:
    roles = db.query(Role).order_by(Role.id).all()
    permissions = db.query(Permission).order_by(Permission.id).all()
    role_perms = db.query(RolePermission).order_by(RolePermission.id).all()
    departments = db.query(Department).order_by(Department.id).all()
    users = db.query(User).order_by(User.id).all()
    user_roles = db.query(UserRole).order_by(UserRole.id).all()
    workflow_defs = db.query(WorkflowDefinition).order_by(WorkflowDefinition.id).all()
    assignment_rules = db.query(AssignmentRule).order_by(AssignmentRule.id).all()
    sla_policies = db.query(SlaPolicy).order_by(SlaPolicy.id).all()

    role_by_id = {r.id: r for r in roles}
    perm_by_id = {p.id: p for p in permissions}
    user_by_id = {u.id: u for u in users}
    dept_by_id = {d.id: d for d in departments}

    return {
        "meta": {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "version": 1,
            "counts": {
                "roles": len(roles),
                "permissions": len(permissions),
                "role_permissions": len(role_perms),
                "departments": len(departments),
                "users": len(users),
                "user_roles": len(user_roles),
                "workflow_definitions": len(workflow_defs),
                "assignment_rules": len(assignment_rules),
                "sla_policies": len(sla_policies),
            },
        },
        "roles": [
            {
                "name": r.name,
                "display_name": r.display_name,
                "is_singleton": bool(r.is_singleton),
            }
            for r in roles
        ],
        "permissions": [
            {
                "name": p.name,
                "code": p.code,
            }
            for p in permissions
        ],
        "role_permissions": [
            {
                "role": role_by_id[rp.role_id].name if rp.role_id in role_by_id else None,
                "permission_code": (
                    perm_by_id[rp.permission_id].code
                    if rp.permission_id in perm_by_id
                    else None
                ),
                "permission_name": (
                    perm_by_id[rp.permission_id].name
                    if rp.permission_id in perm_by_id
                    else None
                ),
            }
            for rp in role_perms
            if rp.role_id in role_by_id and rp.permission_id in perm_by_id
        ],
        "departments": [
            {
                "name": d.name,
                "parent_name": (
                    dept_by_id[d.parent_id].name
                    if d.parent_id and d.parent_id in dept_by_id
                    else None
                ),
                "head_username": (
                    user_by_id[d.head_user_id].username
                    if d.head_user_id and d.head_user_id in user_by_id
                    else None
                ),
            }
            for d in departments
        ],
        "users": [
            {
                "username": u.username,
                "email": u.email,
                "mobile": u.mobile,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "national_id": u.national_id,
                "father_name": u.father_name,
                "account_number": u.account_number,
                "card_number": u.card_number,
                "sheba_number": u.sheba_number,
                "profile_pic": u.profile_pic,
                "hashed_password": u.hashed_password,
                "is_active": bool(u.is_active),
                "department_name": (
                    dept_by_id[u.department_id].name
                    if u.department_id and u.department_id in dept_by_id
                    else None
                ),
                "manager_username": (
                    user_by_id[u.manager_id].username
                    if u.manager_id and u.manager_id in user_by_id
                    else None
                ),
                "created_at": _dt(u.created_at),
            }
            for u in users
        ],
        "user_roles": [
            {
                "username": user_by_id[ur.user_id].username
                if ur.user_id in user_by_id
                else None,
                "role": role_by_id[ur.role_id].name if ur.role_id in role_by_id else None,
                "is_active": bool(ur.is_active),
            }
            for ur in user_roles
            if ur.user_id in user_by_id and ur.role_id in role_by_id
        ],
        "workflow_definitions": [
            {
                "code": w.code,
                "name": w.name,
                "ref_type": w.ref_type,
                "steps_config": w.steps_config,
            }
            for w in workflow_defs
        ],
        "assignment_rules": [
            {
                "role": role_by_id[ar.role_id].name if ar.role_id in role_by_id else None,
                "role_id_legacy": ar.role_id if ar.role_id not in role_by_id else None,
                "strategy": ar.strategy,
                "is_active": bool(ar.is_active),
            }
            for ar in assignment_rules
        ],
        "sla_policies": [
            {
                "ref_type": sp.ref_type,
                "step_order": sp.step_order,
                "max_minutes": sp.max_minutes,
                "escalate_to_role": (
                    role_by_id[sp.escalate_to_role_id].name
                    if sp.escalate_to_role_id and sp.escalate_to_role_id in role_by_id
                    else None
                ),
                "is_active": bool(sp.is_active),
            }
            for sp in sla_policies
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export RBAC + workflow config to JSON")
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "dumps" / "rbac_workflow.json"),
        help="مسیر فایل خروجی JSON",
    )
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        payload = export_all(db)
    finally:
        db.close()

    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = payload["meta"]["counts"]
    print(f"Exported → {out}")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
