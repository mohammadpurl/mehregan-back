"""
وارد کردن کاربران، نقش‌ها، مجوزها و تنظیمات workflow از JSON به دیتابیس هدف.

Upsert با کلید طبیعی:
  role.name | permission.code (یا name) | user.username | department.name
  workflow_definitions.code | sla_policies (ref_type, step_order)

اجرا روی ماشین محلی:
  python scripts/import_rbac_workflow.py -i dumps/rbac_workflow.json

اجرا داخل داکر (پیشنهادی):
  # ۱) کپی فایل JSON به کانتینر
  docker compose cp dumps/rbac_workflow.json mehregan-backend:/tmp/rbac_workflow.json

  # ۲) ایمپورت
  docker compose exec backend python scripts/import_rbac_workflow.py -i /tmp/rbac_workflow.json

گزینه‌ها:
  --skip-users     فقط RBAC + workflow (بدون users/departments/user_roles)
  --dry-run        فقط گزارش؛ بدون commit
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


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def _get_role(db, name: str | None) -> Role | None:
    if not name:
        return None
    return db.query(Role).filter(Role.name == name).first()


def _get_permission(db, *, code: str | None, name: str | None) -> Permission | None:
    if code:
        row = db.query(Permission).filter(Permission.code == code).first()
        if row:
            return row
    if name:
        return db.query(Permission).filter(Permission.name == name).first()
    return None


def import_payload(db, payload: dict, *, skip_users: bool, dry_run: bool) -> dict:
    stats = {
        "roles_upserted": 0,
        "permissions_upserted": 0,
        "role_permissions_upserted": 0,
        "departments_upserted": 0,
        "users_upserted": 0,
        "user_roles_upserted": 0,
        "workflow_definitions_upserted": 0,
        "assignment_rules_upserted": 0,
        "sla_policies_upserted": 0,
        "skipped": 0,
        "warnings": [],
    }

    # 1) roles
    for item in payload.get("roles") or []:
        name = (item.get("name") or "").strip()
        if not name:
            stats["skipped"] += 1
            continue
        row = db.query(Role).filter(Role.name == name).first()
        if not row:
            row = Role(name=name)
            db.add(row)
        row.display_name = item.get("display_name")
        row.is_singleton = bool(item.get("is_singleton", False))
        stats["roles_upserted"] += 1
    db.flush()

    # 2) permissions
    for item in payload.get("permissions") or []:
        name = (item.get("name") or "").strip()
        code = (item.get("code") or None) or None
        if code:
            code = str(code).strip() or None
        if not name and not code:
            stats["skipped"] += 1
            continue
        row = _get_permission(db, code=code, name=name)
        if not row:
            row = Permission(name=name or code, code=code)
            db.add(row)
        else:
            if name:
                row.name = name
            if code:
                row.code = code
        stats["permissions_upserted"] += 1
    db.flush()

    # 3) role_permissions
    for item in payload.get("role_permissions") or []:
        role = _get_role(db, item.get("role"))
        perm = _get_permission(
            db,
            code=item.get("permission_code"),
            name=item.get("permission_name"),
        )
        if not role or not perm:
            stats["warnings"].append(
                f"role_permission skip: role={item.get('role')} "
                f"perm={item.get('permission_code') or item.get('permission_name')}"
            )
            stats["skipped"] += 1
            continue
        exists = (
            db.query(RolePermission)
            .filter(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == perm.id,
            )
            .first()
        )
        if not exists:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        stats["role_permissions_upserted"] += 1
    db.flush()

    if not skip_users:
        # 4) departments (parents first; head later)
        dept_items = list(payload.get("departments") or [])
        # pass 1: create/update without parent/head
        for item in dept_items:
            name = (item.get("name") or "").strip()
            if not name:
                stats["skipped"] += 1
                continue
            row = db.query(Department).filter(Department.name == name).first()
            if not row:
                row = Department(name=name)
                db.add(row)
            stats["departments_upserted"] += 1
        db.flush()

        # pass 2: parents
        for item in dept_items:
            name = (item.get("name") or "").strip()
            parent_name = (item.get("parent_name") or "").strip() or None
            if not name:
                continue
            row = db.query(Department).filter(Department.name == name).first()
            if not row:
                continue
            if parent_name:
                parent = db.query(Department).filter(Department.name == parent_name).first()
                row.parent_id = parent.id if parent else None
            else:
                row.parent_id = None
        db.flush()

        # 5) users (without manager first)
        user_items = list(payload.get("users") or [])
        for item in user_items:
            username = (item.get("username") or "").strip()
            if not username:
                stats["skipped"] += 1
                continue
            hashed = item.get("hashed_password")
            if not hashed:
                stats["warnings"].append(f"user skip (no hashed_password): {username}")
                stats["skipped"] += 1
                continue
            row = db.query(User).filter(User.username == username).first()
            if not row:
                row = User(username=username, hashed_password=hashed)
                db.add(row)
            row.hashed_password = hashed
            row.email = item.get("email")
            row.mobile = item.get("mobile")
            row.first_name = item.get("first_name")
            row.last_name = item.get("last_name")
            row.national_id = item.get("national_id")
            row.father_name = item.get("father_name")
            row.account_number = item.get("account_number")
            row.card_number = item.get("card_number")
            row.sheba_number = item.get("sheba_number")
            row.profile_pic = item.get("profile_pic")
            row.is_active = bool(item.get("is_active", True))
            created_at = _parse_dt(item.get("created_at"))
            if created_at and not row.id:
                row.created_at = created_at
            dept_name = (item.get("department_name") or "").strip() or None
            if dept_name:
                dept = db.query(Department).filter(Department.name == dept_name).first()
                row.department_id = dept.id if dept else None
            else:
                row.department_id = None
            stats["users_upserted"] += 1
        db.flush()

        # pass: managers
        for item in user_items:
            username = (item.get("username") or "").strip()
            manager_username = (item.get("manager_username") or "").strip() or None
            if not username:
                continue
            row = db.query(User).filter(User.username == username).first()
            if not row:
                continue
            if manager_username:
                mgr = db.query(User).filter(User.username == manager_username).first()
                row.manager_id = mgr.id if mgr else None
            else:
                row.manager_id = None
        db.flush()

        # pass: department heads
        for item in dept_items:
            name = (item.get("name") or "").strip()
            head_username = (item.get("head_username") or "").strip() or None
            if not name:
                continue
            row = db.query(Department).filter(Department.name == name).first()
            if not row:
                continue
            if head_username:
                head = db.query(User).filter(User.username == head_username).first()
                row.head_user_id = head.id if head else None
            else:
                row.head_user_id = None
        db.flush()

        # 6) user_roles
        for item in payload.get("user_roles") or []:
            username = (item.get("username") or "").strip()
            role_name = (item.get("role") or "").strip()
            user = db.query(User).filter(User.username == username).first() if username else None
            role = _get_role(db, role_name)
            if not user or not role:
                stats["warnings"].append(
                    f"user_role skip: user={username} role={role_name}"
                )
                stats["skipped"] += 1
                continue
            row = (
                db.query(UserRole)
                .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
                .first()
            )
            if not row:
                row = UserRole(user_id=user.id, role_id=role.id)
                db.add(row)
            row.is_active = bool(item.get("is_active", True))
            stats["user_roles_upserted"] += 1
        db.flush()

    # 7) workflow_definitions
    for item in payload.get("workflow_definitions") or []:
        code = (item.get("code") or "").strip()
        if not code:
            stats["skipped"] += 1
            continue
        row = db.query(WorkflowDefinition).filter(WorkflowDefinition.code == code).first()
        if not row:
            row = WorkflowDefinition(code=code, name=item.get("name") or code)
            db.add(row)
        row.name = item.get("name") or code
        row.ref_type = item.get("ref_type")
        row.steps_config = item.get("steps_config")
        stats["workflow_definitions_upserted"] += 1
    db.flush()

    # 8) assignment_rules
    for item in payload.get("assignment_rules") or []:
        role = _get_role(db, item.get("role"))
        role_id = role.id if role else item.get("role_id_legacy")
        if not role_id:
            stats["warnings"].append(f"assignment_rule skip: {item}")
            stats["skipped"] += 1
            continue
        strategy = (item.get("strategy") or "").strip()
        row = (
            db.query(AssignmentRule)
            .filter(
                AssignmentRule.role_id == int(role_id),
                AssignmentRule.strategy == strategy,
            )
            .first()
        )
        if not row:
            row = AssignmentRule(role_id=int(role_id), strategy=strategy)
            db.add(row)
        row.is_active = bool(item.get("is_active", True))
        stats["assignment_rules_upserted"] += 1
    db.flush()

    # 9) sla_policies
    for item in payload.get("sla_policies") or []:
        ref_type = (item.get("ref_type") or "").strip()
        step_order = item.get("step_order")
        if not ref_type or step_order is None:
            stats["skipped"] += 1
            continue
        row = (
            db.query(SlaPolicy)
            .filter(
                SlaPolicy.ref_type == ref_type,
                SlaPolicy.step_order == int(step_order),
            )
            .first()
        )
        if not row:
            row = SlaPolicy(
                ref_type=ref_type,
                step_order=int(step_order),
                max_minutes=int(item.get("max_minutes") or 0),
            )
            db.add(row)
        row.max_minutes = int(item.get("max_minutes") or 0)
        esc = _get_role(db, item.get("escalate_to_role"))
        row.escalate_to_role_id = esc.id if esc else None
        row.is_active = bool(item.get("is_active", True))
        stats["sla_policies_upserted"] += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Import RBAC + workflow config from JSON")
    parser.add_argument("-i", "--input", required=True, help="مسیر فایل JSON")
    parser.add_argument(
        "--skip-users",
        action="store_true",
        help="کاربران/واحدها/user_roles را ایمپورت نکن",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="بدون ذخیره در دیتابیس",
    )
    args = parser.parse_args()

    path = Path(args.input)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        stats = import_payload(
            db,
            payload,
            skip_users=args.skip_users,
            dry_run=args.dry_run,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    mode = "DRY-RUN" if args.dry_run else "COMMITTED"
    print(f"Import {mode} from {path}")
    for key, value in stats.items():
        if key == "warnings":
            continue
        print(f"  {key}: {value}")
    for warning in stats.get("warnings") or []:
        print(f"  WARN: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
