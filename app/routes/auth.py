from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
from uuid import uuid4
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES

from app.schemas.auth import LoginRequest

from app.core.database import get_db
from app.core.rate_limit import auth_rate_limit, limiter
from app.schemas.auth import TokenResponse
from app.schemas.menu import NavMenuItemOut
from app.schemas.user import AuthMeResponse, UserProfileResponse, UserProfileUpdate
from app.services.auth import (
    authenticate_user,
    create_access_token,
)
from app.services.nav_menu import filter_nav_menu
from app.services.permission import build_user_auth_context, get_user_permissions_db
from app.services.user_profile import (
    remove_user_avatar,
    serialize_user_profile,
    serialize_user_profile_with_auth,
    update_user_profile,
    upload_user_avatar,
)
from app.dependencies.auth import get_current_active_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response_for_user(db: Session, user) -> TokenResponse:
    session_id = str(uuid4())
    auth_ctx = build_user_auth_context(db, user.id)
    roles = auth_ctx["roles"]
    permissions = auth_ctx["permissions"]
    access_token = create_access_token(
        subject=user.username,
        full_name=user.full_name,
        pic=user.profile_pic_url(),
        extra_claims={
            "sessionId": session_id,
            "userId": user.id,
            "roles": roles,
            "permissions": permissions,
        },
    )
    return TokenResponse(
        accessToken=access_token,
        access_token=access_token,
        tokenType="bearer",
        token_type="bearer",
        sessionId=session_id,
        sessionExpiry=int(
            (
                datetime.now(timezone.utc)
                + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            ).timestamp()
        ),
        userId=user.id,
        roles=roles,
        permissions=permissions,
    )


def _login_or_401(db: Session, username: str, password: str):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response_for_user(db, user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(auth_rate_limit())
def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    ورود — همان قرارداد فرانت (JSON).
    Body: { "username": "...", "password": "..." }
    Response: accessToken, sessionId, sessionExpiry, ...
    """
    return _login_or_401(db, payload.username, payload.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
@limiter.limit(auth_rate_limit())
def login_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """فقط برای Authorize در Swagger؛ فرانت این مسیر را صدا نمی‌زند."""
    return _login_or_401(db, form_data.username, form_data.password)


@router.get(
    "/me",
    response_model=AuthMeResponse,
    response_model_exclude_none=False,
)
def get_my_profile(
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    return serialize_user_profile_with_auth(db, user)


@router.get("/menus", response_model=list[NavMenuItemOut])
def get_my_menus(
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """منوی فیلترشده بر اساس مجوزهای فعال کاربر (منبع حقیقت برای UI)."""
    perms = get_user_permissions_db(db, user.id)
    return filter_nav_menu(perms)


@router.patch(
    "/profile",
    response_model=UserProfileResponse,
    response_model_exclude_none=False,
)
@router.put(
    "/profile",
    response_model=UserProfileResponse,
    response_model_exclude_none=False,
)
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    updated = update_user_profile(db, user, payload)
    return serialize_user_profile(updated)


@router.post(
    "/profile/avatar",
    response_model=UserProfileResponse,
    response_model_exclude_none=False,
)
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    updated = await upload_user_avatar(db, user, file)
    return serialize_user_profile(updated, bust_avatar_cache=True)


@router.delete(
    "/profile/avatar",
    response_model=UserProfileResponse,
    response_model_exclude_none=False,
)
def delete_my_avatar(
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    updated = remove_user_avatar(db, user)
    return serialize_user_profile(updated)
