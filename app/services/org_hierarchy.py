from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.user import User
from app.services.department import build_department_tree, _user_display_name
from app.services.org import get_manager_chain


def get_user_org_position(db: Session, user_id: int) -> dict | None:
    user = db.get(User, user_id)
    if not user:
        return None

    manager = db.get(User, user.manager_id) if user.manager_id else None
    dept = db.get(Department, user.department_id) if user.department_id else None
    dept_head = None
    if dept and getattr(dept, "head_user_id", None):
        dept_head = db.get(User, dept.head_user_id)

    chain = get_manager_chain(db, user_id, level=10)
    return {
        "user_id": user.id,
        "userId": user.id,
        "username": user.username,
        "full_name": _user_display_name(user),
        "fullName": _user_display_name(user),
        "department_id": user.department_id,
        "departmentId": user.department_id,
        "department_name": dept.name if dept else None,
        "departmentName": dept.name if dept else None,
        "manager_id": user.manager_id,
        "managerId": user.manager_id,
        "manager_name": _user_display_name(manager),
        "managerName": _user_display_name(manager),
        "department_head_id": dept.head_user_id if dept else None,
        "departmentHeadId": dept.head_user_id if dept else None,
        "department_head_name": _user_display_name(dept_head),
        "departmentHeadName": _user_display_name(dept_head),
        "manager_chain": [
            {
                "id": m.id,
                "username": m.username,
                "full_name": _user_display_name(m),
                "fullName": _user_display_name(m),
            }
            for m in chain
        ],
    }


def list_users_org_flat(db: Session) -> list[dict]:
    users = db.query(User).order_by(User.id).all()
    dept_names = {
        d.id: d.name for d in db.query(Department.id, Department.name).all()
    }
    out: list[dict] = []
    for user in users:
        manager = db.get(User, user.manager_id) if user.manager_id else None
        out.append(
            {
                "id": user.id,
                "username": user.username,
                "full_name": _user_display_name(user),
                "fullName": _user_display_name(user),
                "department_id": user.department_id,
                "departmentId": user.department_id,
                "department_name": dept_names.get(user.department_id),
                "departmentName": dept_names.get(user.department_id),
                "manager_id": user.manager_id,
                "managerId": user.manager_id,
                "manager_name": _user_display_name(manager),
                "managerName": _user_display_name(manager),
                "is_active": user.is_active,
                "isActive": user.is_active,
            }
        )
    return out


def get_org_hierarchy(db: Session) -> dict:
    return {
        "departments": build_department_tree(db),
        "users": list_users_org_flat(db),
    }
