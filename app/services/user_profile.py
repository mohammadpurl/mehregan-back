import time
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import API_PUBLIC_BASE_URL, UPLOAD_DIRECTORY
from app.models.user import User
from app.schemas.user import AuthMeResponse, UserProfileResponse, UserProfileUpdate
from app.services.permission import build_user_auth_context

from app.constants.upload_limits import AVATAR_ALLOWED_EXTENSIONS, AVATAR_MAX_BYTES

ALLOWED_AVATAR_EXTENSIONS = set(AVATAR_ALLOWED_EXTENSIONS)
CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def _absolute_pic_url(relative_pic: str) -> str:
    if not relative_pic:
        return ""
    if relative_pic.startswith("http://") or relative_pic.startswith("https://"):
        return relative_pic
    base = (API_PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return relative_pic
    return f"{base}{relative_pic}"


def get_user_profile(user: User, *, bust_avatar_cache: bool = False) -> dict:
    """دیکشنری کامل پروفایل — همیشه شامل card/sheba (حتی null)."""
    cache_bust = int(time.time()) if bust_avatar_cache else None
    pic = user.profile_pic_url(cache_bust=cache_bust)
    card = getattr(user, "card_number", None)
    sheba = getattr(user, "sheba_number", None)
    account = getattr(user, "account_number", None)
    return {
        "profile_version": 2,
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "mobile": user.mobile,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "national_id": user.national_id,
        "father_name": user.father_name,
        "account_number": account,
        "accountNumber": account,
        "card_number": card,
        "cardNumber": card,
        "sheba_number": sheba,
        "shebaNumber": sheba,
        "pic": pic,
        "picUrl": _absolute_pic_url(pic),
        "full_name": user.full_name,
    }


def serialize_user_profile(user: User, *, bust_avatar_cache: bool = False) -> UserProfileResponse:
    return UserProfileResponse(**get_user_profile(user, bust_avatar_cache=bust_avatar_cache))


def serialize_user_profile_with_auth(
    db: Session, user: User, *, bust_avatar_cache: bool = False
) -> AuthMeResponse:
    data = get_user_profile(user, bust_avatar_cache=bust_avatar_cache)
    data.update(build_user_auth_context(db, user.id))
    return AuthMeResponse(**data)


def _avatar_dir() -> Path:
    path = UPLOAD_DIRECTORY / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_avatar_extension(file: UploadFile) -> str:
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext in ALLOWED_AVATAR_EXTENSIONS:
            return ext if ext != ".jpeg" else ".jpg"
    content_type = (file.content_type or "").lower()
    ext = CONTENT_TYPE_TO_EXT.get(content_type)
    if ext:
        return ext
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="فرمت تصویر مجاز نیست. jpg، png، webp، gif، heic",
    )


def _delete_avatar_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    safe = relative_path.replace("\\", "/").lstrip("/")
    if ".." in safe or not safe.startswith("avatars/"):
        return
    full = (UPLOAD_DIRECTORY / safe).resolve()
    try:
        full.relative_to(UPLOAD_DIRECTORY.resolve())
    except ValueError:
        return
    if full.is_file():
        full.unlink(missing_ok=True)


async def upload_user_avatar(db: Session, user: User, file: UploadFile) -> User:
    if not file.filename and not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل تصویر ارسال نشده است",
        )

    ext = _resolve_avatar_extension(file)
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل خالی است",
        )
    if len(content) > AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"حداکثر حجم تصویر {AVATAR_MAX_BYTES // (1024 * 1024)} مگابایت است",
        )

    _delete_avatar_file(user.profile_pic)

    avatar_dir = _avatar_dir()
    for old in avatar_dir.glob(f"user_{user.id}.*"):
        old.unlink(missing_ok=True)

    filename = f"user_{user.id}{ext}"
    dest = avatar_dir / filename
    dest.write_bytes(content)

    user.profile_pic = f"avatars/{filename}"
    db.commit()
    db.refresh(user)
    return user


def remove_user_avatar(db: Session, user: User) -> User:
    _delete_avatar_file(user.profile_pic)
    user.profile_pic = None
    db.commit()
    db.refresh(user)
    return user


_PROFILE_FIELDS = frozenset(
    {
        "email",
        "mobile",
        "first_name",
        "last_name",
        "national_id",
        "father_name",
        "account_number",
        "card_number",
        "sheba_number",
    }
)


def update_user_profile(db: Session, user: User, payload: UserProfileUpdate) -> User:
    fields_set = payload.model_fields_set
    data = payload.model_dump(exclude_unset=True)
    data = {k: v for k, v in data.items() if k in _PROFILE_FIELDS}

    if "email" in data and data["email"] is not None:
        exists = (
            db.query(User)
            .filter(User.email == data["email"], User.id != user.id)
            .first()
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این ایمیل قبلاً استفاده شده است",
            )

    if "mobile" in data and data["mobile"] is not None:
        exists = (
            db.query(User)
            .filter(User.mobile == data["mobile"], User.id != user.id)
            .first()
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این شماره موبایل قبلاً استفاده شده است",
            )

    if "national_id" in data and data["national_id"] is not None:
        exists = (
            db.query(User)
            .filter(User.national_id == data["national_id"], User.id != user.id)
            .first()
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این کد ملی قبلاً ثبت شده است",
            )

    for key, value in data.items():
        if key in ("account_number", "card_number", "sheba_number"):
            continue
        setattr(user, key, value)

    if "account_number" in fields_set:
        user.account_number = payload.account_number
    if "card_number" in fields_set:
        user.card_number = payload.card_number
    if "sheba_number" in fields_set:
        user.sheba_number = payload.sheba_number

    try:
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        msg = str(exc).lower()
        if (
            "account_number" in msg
            or "card_number" in msg
            or "sheba_number" in msg
            or "column" in msg
        ):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "ستون‌های account_number / card_number / sheba_number در دیتابیس وجود ندارند. "
                    "سرور را restart کنید یا: python scripts/apply_schema_patches.py"
                ),
            ) from exc
        raise

    return user
