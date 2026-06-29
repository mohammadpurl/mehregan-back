"""
پاک‌سازی و seed مجدد جداول roles و permissions (+ role_permissions).

قبل از اجرا:
  python scripts/apply_schema_patches.py

اجرا:
  python scripts/reset_rbac.py --yes
  python scripts/reset_rbac.py --yes --grant-super-admin 1

گزینه‌ها:
  --yes                 بدون این پرچم فقط dry-run است
  --grant-super-admin   بعد از seed نقش super-admin را به user_id می‌دهد
  --skip-user-roles     user_roles را پاک/بازیابی نمی‌کند (ممکن است FK خطا بدهد)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.schema_patch import ensure_permissions_schema, ensure_roles_schema, ensure_postgres_sequences
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole
from app.models.workflow_step import WorkflowStep
from app.constants.role_labels import ROLE_DISPLAY_NAMES

# ---------------------------------------------------------------------------
# Permissions: (code, نام فارسی برای ستون name)
# کدهای استفاده‌شده در require_permission() + دسترسی‌های ERP/workflow
# ---------------------------------------------------------------------------
PERMISSIONS: list[tuple[str, str]] = [
    ("*", "دسترسی کامل (فقط super-admin)"),
    ("dashboard.read", "مشاهده داشبورد"),
    ("workflow.read", "مشاهده گردش‌کار"),
    ("workflow.inbox.read", "مشاهده کارتابل"),
    ("workflow.tracking.read", "پیگیری گردش‌کار"),
    ("workflow.all.read", "مشاهده همه درخواست‌های گردش‌کار"),
    ("workflow.approve", "تأیید / رد گردش‌کار"),
    ("procurement.read", "مشاهده تدارکات"),
    ("procurement.write", "ثبت و ویرایش تدارکات"),
    ("inventory.read", "مشاهده انبار"),
    ("inventory.transfer", "انتقال موجودی انبار"),
    ("masterdata.manage", "مدیریت داده‌های پایه"),
    ("admin.manage", "مدیریت سیستم (کاربر، واحد، workflow)"),
    ("item.create", "ایجاد کالا"),
    ("item.read", "مشاهده کالا"),
    ("item.update", "ویرایش کالا"),
    ("item.delete", "حذف کالا"),
    ("item.submit", "ارسال کالا برای تأیید"),
    ("item.*", "مدیریت کامل کالا (wildcard)"),
    ("payment.create", "ثبت درخواست پرداخت / وام"),
    ("payment.approve", "تأیید درخواست پرداخت"),
]

# ---------------------------------------------------------------------------
# Roles: (slug انگلیسی, نام نمایشی فارسی)
# ---------------------------------------------------------------------------
ROLES: list[tuple[str, str]] = [
    (slug, ROLE_DISPLAY_NAMES.get(slug, slug))
    for slug in (
        "super-admin",
        "admin",
        "system_admin",
        "ceo",
        "managing_director",
        "finance_manager",
        "accountant",
        "purchase_manager",
        "procurement_manager",
        "warehouse_manager",
        "warehouse",
        "manager",
        "project_manager",
        "employee",
    )
]

# ---------------------------------------------------------------------------
# نقش → لیست کد permission (یا "*" برای همه)
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super-admin": ["*"],
    "admin": [
        "admin.manage",
        "masterdata.manage",
        "item.*",
        "payment.create",
        "payment.approve",
        "procurement.read",
        "procurement.write",
        "inventory.read",
        "inventory.transfer",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.all.read",
        "workflow.approve",
        "dashboard.read",
    ],
    "system_admin": [
        "admin.manage",
        "masterdata.manage",
        "item.*",
        "payment.create",
        "payment.approve",
        "workflow.approve",
        "workflow.all.read",
        "workflow.tracking.read",
        "workflow.inbox.read",
        "workflow.read",
        "dashboard.read",
    ],
    "ceo": [
        "dashboard.read",
        "workflow.read",
        "workflow.all.read",
        "workflow.tracking.read",
        "workflow.approve",
        "payment.approve",
    ],
    "managing_director": [
        "dashboard.read",
        "workflow.read",
        "workflow.all.read",
        "workflow.tracking.read",
        "workflow.approve",
        "payment.approve",
    ],
    "finance_manager": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "procurement.read",
        "inventory.read",
        "payment.create",
        "payment.approve",
    ],
    "accountant": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "procurement.read",
        "payment.create",
        "payment.approve",
    ],
    "purchase_manager": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "procurement.read",
        "procurement.write",
    ],
    "procurement_manager": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "procurement.read",
        "procurement.write",
    ],
    "warehouse_manager": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "inventory.read",
        "inventory.transfer",
        "item.read",
        "item.create",
        "item.update",
        "item.submit",
    ],
    "warehouse": [
        "dashboard.read",
        "inventory.read",
        "inventory.transfer",
        "item.read",
        "item.create",
        "item.update",
    ],
    "manager": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "payment.create",
    ],
    "project_manager": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "workflow.approve",
        "payment.create",
    ],
    "employee": [
        "dashboard.read",
        "workflow.read",
        "workflow.inbox.read",
        "workflow.tracking.read",
        "payment.create",
    ],
}


def _expand_role_permissions(codes: list[str]) -> list[str]:
    """تبدیل '*' در نقش به همه permissionهای تعریف‌شده (به‌جز خود '*')."""
    if "*" in codes:
        return [c for c, _ in PERMISSIONS if c != "*"]
    return list(codes)


def _backup_user_roles(db: Session) -> list[tuple[int, str]]:
    rows = (
        db.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
        )
        .all()
    )
    return [(int(u), str(r)) for u, r in rows]


def _backup_workflow_step_roles(db: Session) -> list[tuple[int, str]]:
    rows = (
        db.execute(
            select(WorkflowStep.id, Role.name)
            .join(Role, Role.id == WorkflowStep.role_id)
        )
        .all()
    )
    return [(int(sid), str(rname)) for sid, rname in rows]


def _deprecate_existing_roles(db: Session) -> None:
    """workflow_steps به roles FK دارد؛ نقش‌های قدیمی را rename می‌کنیم تا نام‌های جدید جا شوند."""
    for role in db.query(Role).all():
        role.name = f"__deprecated_{role.id}__"
    db.flush()


def _delete_deprecated_roles(db: Session) -> None:
    used_role_ids = {
        r[0]
        for r in db.execute(select(WorkflowStep.role_id).distinct()).all()
        if r[0] is not None
    }
    deprecated = db.query(Role).filter(Role.name.like("__deprecated_%")).all()
    removed = 0
    kept = 0
    for role in deprecated:
        if role.id in used_role_ids:
            kept += 1
            continue
        db.delete(role)
        removed += 1
    db.flush()
    if kept:
        print(
            f"  kept {kept} deprecated role(s) still referenced by workflow_steps"
        )
    print(f"  removed {removed} unused deprecated role(s)")


def _clear_rbac_tables(db: Session) -> None:
    db.execute(delete(RolePermission))
    db.execute(delete(UserRole))
    db.execute(delete(Permission))
    _deprecate_existing_roles(db)
    db.flush()


def _seed(db: Session) -> tuple[dict[str, int], dict[str, int]]:
    perm_by_code: dict[str, int] = {}
    for code, label in PERMISSIONS:
        row = Permission(name=label, code=code)
        db.add(row)
        db.flush()
        perm_by_code[code] = row.id

    role_by_name: dict[str, int] = {}
    for name, label in ROLES:
        row = Role(name=name, display_name=label)
        db.add(row)
        db.flush()
        role_by_name[name] = row.id

    link_count = 0
    for role_name, codes in ROLE_PERMISSIONS.items():
        role_id = role_by_name.get(role_name)
        if not role_id:
            print(f"  WARN: role {role_name!r} not in ROLES list, skip links")
            continue
        for code in _expand_role_permissions(codes):
            perm_id = perm_by_code.get(code)
            if not perm_id:
                print(f"  WARN: permission {code!r} missing, skip for {role_name}")
                continue
            db.add(RolePermission(role_id=role_id, permission_id=perm_id))
            link_count += 1

    print(
        f"  inserted: {len(perm_by_code)} permissions, "
        f"{len(role_by_name)} roles, {link_count} role_permission links"
    )
    return role_by_name, perm_by_code


def _restore_user_roles(
    db: Session,
    backup: list[tuple[int, str]],
    role_by_name: dict[str, int],
) -> None:
    restored = 0
    skipped = 0
    for user_id, role_name in backup:
        role_id = role_by_name.get(role_name)
        if not role_id:
            print(f"  WARN: cannot restore user_roles user={user_id} role={role_name!r}")
            skipped += 1
            continue
        db.add(UserRole(user_id=user_id, role_id=role_id, is_active=True))
        restored += 1
    print(f"  user_roles restored={restored} skipped={skipped}")


def _restore_workflow_step_roles(
    db: Session,
    backup: list[tuple[int, str]],
    role_by_name: dict[str, int],
) -> None:
    restored = 0
    skipped = 0
    for step_id, role_name in backup:
        role_id = role_by_name.get(role_name)
        if not role_id:
            print(
                f"  WARN: cannot restore workflow_steps id={step_id} role={role_name!r}"
            )
            skipped += 1
            continue
        step = db.get(WorkflowStep, step_id)
        if step:
            step.role_id = role_id
            restored += 1
    print(f"  workflow_steps role_id restored={restored} skipped={skipped}")


def _grant_role(db: Session, user_id: int, role_name: str, role_by_name: dict[str, int]) -> None:
    role_id = role_by_name.get(role_name)
    if not role_id:
        raise SystemExit(f"Role {role_name!r} not found after seed")
    exists = (
        db.query(UserRole)
        .filter_by(user_id=user_id, role_id=role_id)
        .first()
    )
    if exists:
        exists.is_active = True
        print(f"  user {user_id} already has role {role_name}, activated")
        return
    db.add(UserRole(user_id=user_id, role_id=role_id, is_active=True))
    print(f"  granted role {role_name} to user {user_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and seed RBAC tables")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete and re-insert (otherwise dry-run)",
    )
    parser.add_argument(
        "--grant-super-admin",
        type=int,
        metavar="USER_ID",
        help="Assign super-admin role to this user after seed",
    )
    parser.add_argument(
        "--skip-user-roles",
        action="store_true",
        help="Do not backup/restore user_roles (will fail if roles deleted with FK)",
    )
    args = parser.parse_args()

    ensure_permissions_schema(engine)
    ensure_roles_schema(engine)

    db = SessionLocal()
    try:
        role_count = db.query(Role).count()
        perm_count = db.query(Permission).count()
        ur_count = db.query(UserRole).count()
        rp_count = db.query(RolePermission).count()

        print(f"Database: {engine.url.render_as_string(hide_password=True)}")
        print(
            f"Current: roles={role_count} permissions={perm_count} "
            f"user_roles={ur_count} role_permissions={rp_count}"
        )
        print(f"Will seed: {len(ROLES)} roles, {len(PERMISSIONS)} permissions")

        if not args.yes:
            print("\nDry-run only. Re-run with --yes to apply.")
            return

        user_roles_backup: list[tuple[int, str]] = []
        step_roles_backup: list[tuple[int, str]] = []
        if not args.skip_user_roles:
            user_roles_backup = _backup_user_roles(db)
            print(f"  backed up {len(user_roles_backup)} user_roles rows")
        step_roles_backup = _backup_workflow_step_roles(db)
        print(f"  backed up {len(step_roles_backup)} workflow_steps role mappings")

        print(
            "Clearing role_permissions, user_roles, permissions; "
            "deprecating old roles (workflow_steps FK) ..."
        )
        _clear_rbac_tables(db)

        print("Seeding roles and permissions ...")
        role_by_name, _ = _seed(db)

        if step_roles_backup:
            _restore_workflow_step_roles(db, step_roles_backup, role_by_name)
        _delete_deprecated_roles(db)

        if not args.skip_user_roles and user_roles_backup:
            _restore_user_roles(db, user_roles_backup, role_by_name)

        if args.grant_super_admin is not None:
            _grant_role(db, args.grant_super_admin, "super-admin", role_by_name)

        db.commit()
        ensure_postgres_sequences(engine)
        print("\nRBAC reset completed successfully.")
        print(
            "Next: re-login users so JWT/session picks up new permissions; "
            "assign roles to users missing from backup."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
