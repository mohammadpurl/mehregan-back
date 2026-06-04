# app/services/auth.py
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.models.user import User
from app.schemas.auth import RegisterRequest
from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_password_hash, verify_password
from app.services.permission import get_user_permissions


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, payload: RegisterRequest) -> User:
    if get_user_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="این نام کاربری قبلاً گرفته شده است")

    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="این ایمیل قبلاً استفاده شده است")

    today = date.today()
    reset_date = (
        date(today.year, today.month + 1, 1)
        if today.month < 12
        else date(today.year + 1, 1, 1)
    )

    user = User(
        username=payload.username,
        email=payload.email,
        mobile=payload.mobile,
        hashed_password=get_password_hash(payload.password),  # حالا درست کار می‌کند
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(
    subject: str,
    extra_claims: dict | None = None,
    full_name: str | None = None,
    pic: str | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    display_name = full_name or subject
    to_encode = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "type": "access",
        "userName": subject,
        "fullName": display_name,
        "pic": pic or "",
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str, db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(db, username)
    if user is None:
        raise credentials_exception
    return user
