from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.api_error import api_error_detail
from app.core.config import OAUTH2_TOKEN_URL
from app.core.database import get_db
from app.services.auth import get_current_user as resolve_user_from_token
from app.services.permission import (
    get_user_permissions_db,
    permission_matches,
    user_has_permission_db,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=OAUTH2_TOKEN_URL)


def get_current_user_dep(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    return resolve_user_from_token(token, db)


# Bearer JWT dependency for routes (do not use services.auth.get_current_user in Depends)
get_current_user = get_current_user_dep


def get_current_active_user(
    current_user=Depends(get_current_user_dep),
):
    if not current_user.is_active:
        raise HTTPException(
            status_code=403,
            detail=api_error_detail("USER_INACTIVE", "کاربر غیرفعال است"),
        )
    return current_user


def require_permission(permission_code: str):
    def wrapper(
        current_user=Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ):
        if not user_has_permission_db(db, current_user.id, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=api_error_detail(
                    "PERMISSION_DENIED",
                    "شما دسترسی لازم را ندارید",
                    required_permission=permission_code,
                ),
            )
        return current_user

    return wrapper


def require_any_permission(*permission_codes: str):
    """حداقل یکی از مجوزها (با پشتیبانی wildcard مثل item.*)."""

    codes = tuple(c for c in permission_codes if c)

    def wrapper(
        current_user=Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ):
        if not codes:
            return current_user
        perms = get_user_permissions_db(db, current_user.id)
        if any(permission_matches(perms, code) for code in codes):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=api_error_detail(
                "PERMISSION_DENIED",
                "شما دسترسی لازم را ندارید",
                required_permissions=list(codes),
            ),
        )

    return wrapper
