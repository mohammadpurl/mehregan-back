from app.core.database import SessionLocal
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from sqlalchemy.exc import SQLAlchemyError

db = SessionLocal()


def seed_permissions():
    permissions = [
        "item.create",
        "item.read",
        "item.update",
        "item.delete",
        "item.*",
        "payment.create",
        "payment.approve",
        "inventory.transfer",
    ]

    for code in permissions:
        exists = db.query(Permission).filter_by(code=code).first()
        if not exists:
            db.add(Permission(name=code, code=code))

    db.commit()


def seed_roles():
    roles = [
        "admin",
        "manager",
        "accountant",
        "warehouse",
        "finance_manager",
        "ceo",
        "warehouse_manager",
        "purchase_manager",
    ]

    for role_name in roles:
        exists = db.query(Role).filter_by(name=role_name).first()
        if not exists:
            db.add(Role(name=role_name))

    db.commit()


def assign_permissions_to_roles():
    admin = db.query(Role).filter_by(name="admin").first()
    all_permissions = db.query(Permission).all()
    if not admin:
        return

    def add_role_permission(role_id: int, permission_id: int):
        exists = (
            db.query(RolePermission)
            .filter_by(role_id=role_id, permission_id=permission_id)
            .first()
        )
        if not exists:
            db.add(RolePermission(role_id=role_id, permission_id=permission_id))

    # admin → همه دسترسی‌ها
    for perm in all_permissions:
        add_role_permission(admin.id, perm.id)

    # accountant
    accountant = db.query(Role).filter_by(name="accountant").first()
    if accountant:
        for perm in all_permissions:
            if perm.code.startswith("payment"):
                add_role_permission(accountant.id, perm.id)

    # warehouse
    warehouse = db.query(Role).filter_by(name="warehouse").first()
    if warehouse:
        for perm in all_permissions:
            if perm.code.startswith("item") or perm.code.startswith("inventory"):
                add_role_permission(warehouse.id, perm.id)

    db.commit()


if __name__ == "__main__":
    seed_roles()
    try:
        seed_permissions()
        assign_permissions_to_roles()
    except SQLAlchemyError:
        db.rollback()
        print("RBAC roles seeded; permission seed skipped due to schema mismatch.")
    else:
        print("RBAC seeded successfully")
