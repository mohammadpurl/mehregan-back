from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.security import get_password_hash
from app.models.department import Department
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.user_list import UserCreate, UserUpdate
from app.services import rbac
SORT_FIELD_MAP = {
    "full_name": "first_name",
    "phone": "mobile",
    "role_name": "role_name",
}


def _join_name(first_name: str | None, last_name: str | None) -> str | None:
    name = " ".join(
        p.strip() for p in (first_name, last_name) if p and p.strip()
    )
    return name or None


def _manager_display_name(manager: User | None) -> str | None:
    if not manager:
        return None
    return _join_name(manager.first_name, manager.last_name) or manager.username


def _primary_role_subquery():
    return (
        select(
            UserRole.user_id.label("user_id"),
            func.min(UserRole.role_id).label("role_id"),
        )
        .where(UserRole.is_active.is_(True))
        .group_by(UserRole.user_id)
        .subquery()
    )


def _build_users_query(
    db: Session,
    *,
    user_id: int | None = None,
    username: str | None = None,
    email: str | None = None,
    search: str | None = None,
):
    Manager = aliased(User)
    role_sq = _primary_role_subquery()

    query = (
        db.query(User, Manager, Role)
        .outerjoin(Manager, User.manager_id == Manager.id)
        .outerjoin(role_sq, role_sq.c.user_id == User.id)
        .outerjoin(Role, Role.id == role_sq.c.role_id)
    )

    if user_id is not None:
        query = query.filter(User.id == user_id)
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))
    if email:
        query = query.filter(User.email.ilike(f"%{email}%"))
    if search:
        query = query.filter(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.mobile.ilike(f"%{search}%"),
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.national_id.ilike(f"%{search}%"),
                User.card_number.ilike(f"%{search}%"),
                User.sheba_number.ilike(f"%{search}%"),
            )
        )
    return query, Manager, Role


def _resolve_sort_column(sort_by: str, Role_model):
    mapped = SORT_FIELD_MAP.get(sort_by, sort_by)
    if mapped == "role_name":
        return Role_model.name
    return getattr(User, mapped, None) or User.id


def list_users(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 10,
    sort_by: str = "id",
    sort_order: str = "desc",
    user_id: int | None = None,
    username: str | None = None,
    email: str | None = None,
    search: str | None = None,
) -> list[dict]:
    query, Manager, Role_model = _build_users_query(
        db,
        user_id=user_id,
        username=username,
        email=email,
        search=search,
    )

    sort_col = _resolve_sort_column(sort_by, Role_model)
    if sort_order.lower() == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    rows = query.offset(offset).limit(limit).all()
    items: list[dict] = []
    dept_names = {d.id: d.name for d in db.query(Department).all()}
    for user, manager, role in rows:
        full_name = _join_name(user.first_name, user.last_name)
        items.append(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": full_name,
                "phone": user.mobile,
                "is_active": user.is_active,
                "role_id": role.id if role else None,
                "role_name": role.name if role else None,
                "role_display_name": (
                    (role.display_name or role.name) if role else None
                ),
                "manager_id": user.manager_id,
                "manager_name": _manager_display_name(manager),
                "department_id": user.department_id,
                "department_name": dept_names.get(user.department_id),
                "card_number": user.card_number,
                "cardNumber": user.card_number,
                "sheba_number": user.sheba_number,
                "shebaNumber": user.sheba_number,
            }
        )
    return items


def get_user_list_item(db: Session, user_id: int) -> dict | None:
    items = list_users(db, offset=0, limit=1, user_id=user_id)
    return items[0] if items else None


def create_user_admin(db: Session, payload: UserCreate) -> dict:
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این نام کاربری قبلاً گرفته شده است",
        )

    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این ایمیل قبلاً استفاده شده است",
        )

    if payload.phone and db.query(User).filter(User.mobile == payload.phone).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این شماره موبایل قبلاً استفاده شده است",
        )

    if payload.manager_id is not None:
        manager = db.get(User, payload.manager_id)
        if not manager:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="مدیر یافت نشد",
            )

    if payload.role_id is not None and not db.get(Role, payload.role_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نقش یافت نشد",
        )

    if payload.department_id is not None and not db.get(Department, payload.department_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="واحد سازمانی یافت نشد",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        mobile=payload.phone,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        card_number=payload.card_number,
        sheba_number=payload.sheba_number,
        is_active=payload.is_active,
        manager_id=payload.manager_id,
        department_id=payload.department_id,
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.flush()

    if payload.role_id is not None:
        rbac.assign_role_to_user(db, user.id, payload.role_id, commit=False)

    db.commit()
    db.refresh(user)

    item = get_user_list_item(db, user.id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="کاربر ایجاد شد ولی بازیابی اطلاعات ناموفق بود",
        )
    return item


def update_user_admin(db: Session, user_id: int, payload: UserUpdate) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد",
        )

    if payload.username is not None:
        username = payload.username.strip()
        if not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="نام کاربری نمی‌تواند خالی باشد",
            )
        other = (
            db.query(User)
            .filter(User.username == username, User.id != user_id)
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این نام کاربری قبلاً استفاده شده است",
            )
        user.username = username

    if payload.email is not None:
        other = (
            db.query(User)
            .filter(User.email == payload.email, User.id != user_id)
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این ایمیل قبلاً استفاده شده است",
            )
        user.email = payload.email

    if payload.phone is not None:
        other = (
            db.query(User)
            .filter(User.mobile == payload.phone, User.id != user_id)
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این شماره موبایل قبلاً استفاده شده است",
            )
        user.mobile = payload.phone

    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        user.last_name = payload.last_name.strip()
    if payload.card_number is not None:
        user.card_number = payload.card_number or None
    if payload.sheba_number is not None:
        user.sheba_number = payload.sheba_number or None
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password:
        plain = payload.password.strip()
        if len(plain) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="رمز عبور باید حداقل ۶ کاراکتر باشد",
            )
        user.hashed_password = get_password_hash(plain)

    if payload.manager_id is not None:
        if payload.manager_id == 0:
            user.manager_id = None
        else:
            if payload.manager_id == user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="کاربر نمی‌تواند مدیر خودش باشد",
                )
            manager = db.get(User, payload.manager_id)
            if not manager:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="مدیر یافت نشد",
                )
            user.manager_id = payload.manager_id

    if payload.department_id is not None:
        if payload.department_id == 0:
            user.department_id = None
        else:
            dept = db.get(Department, payload.department_id)
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="واحد سازمانی یافت نشد",
                )
            user.department_id = payload.department_id

    if payload.role_id is not None:
        if not db.get(Role, payload.role_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="نقش یافت نشد",
            )
        active_roles = [
            ur for ur in user.user_roles if ur.is_active and ur.role_id != payload.role_id
        ]
        for ur in active_roles:
            ur.is_active = False
        rbac.assign_role_to_user(db, user.id, payload.role_id, commit=False)

    db.commit()
    db.refresh(user)

    item = get_user_list_item(db, user.id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="به‌روزرسانی انجام شد ولی بازیابی اطلاعات ناموفق بود",
        )
    return item


def delete_user_admin(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد",
        )
    db.query(UserRole).filter_by(user_id=user_id).delete()
    db.delete(user)
    db.commit()


def count_users(
    db: Session,
    *,
    user_id: int | None = None,
    username: str | None = None,
    email: str | None = None,
    search: str | None = None,
) -> int:
    query, _, _ = _build_users_query(
        db,
        user_id=user_id,
        username=username,
        email=email,
        search=search,
    )
    return query.with_entities(func.count(User.id)).scalar() or 0
