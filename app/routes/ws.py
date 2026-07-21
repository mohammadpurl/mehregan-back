from fastapi import APIRouter, Query, WebSocket, WebSocketException, status

from app.core.config import ENVIRONMENT
from app.core.database import SessionLocal
from app.core.websocket_manager import manager
from app.services.auth import get_current_user

router = APIRouter()

ACCESS_TOKEN_COOKIE = "erp-access-token"
_IS_PRODUCTION = ENVIRONMENT in {"production", "prod"}


def _token_from_cookie(websocket: WebSocket) -> str | None:
    raw = websocket.cookies.get(ACCESS_TOKEN_COOKIE)
    if raw and str(raw).strip():
        return str(raw).strip()
    return None


def _token_from_query(token: str | None) -> str | None:
    """Query token فقط برای سازگاری legacy؛ در production غیرفعال است (نشت JWT در لاگ/پروکسی)."""
    if _IS_PRODUCTION or not token:
        return None
    cleaned = token.strip()
    return cleaned or None


def _resolve_auth_token(websocket: WebSocket, token: str | None) -> str:
    auth_token = _token_from_cookie(websocket) or _token_from_query(token)
    if not auth_token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="token required",
        )
    return auth_token


def _resolve_user_from_ws_token(token: str):
    db = SessionLocal()
    try:
        user = get_current_user(token, db)
        if not user.is_active:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="inactive user",
            )
        return user
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_authenticated(
    websocket: WebSocket,
    token: str | None = Query(None),
):
    """اتصال با کوکی httpOnly erp-access-token؛ query فقط legacy غیرپروداکشن."""
    auth_token = _resolve_auth_token(websocket, token)
    user = _resolve_user_from_ws_token(auth_token)
    await manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        manager.disconnect(user.id, websocket)


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    token: str | None = Query(None),
):
    """مسیر legacy — کوکی یا query؛ user_id باید با توکن یکی باشد."""
    auth_token = _resolve_auth_token(websocket, token)
    user = _resolve_user_from_ws_token(auth_token)
    if int(user.id) != int(user_id):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="user mismatch",
        )
    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        manager.disconnect(user_id, websocket)
