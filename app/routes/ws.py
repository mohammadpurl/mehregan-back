from fastapi import APIRouter, Query, WebSocket, WebSocketException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.websocket_manager import manager
from app.services.auth import get_current_user

router = APIRouter()


def _resolve_user_from_ws_token(token: str | None):
    if not token or not str(token).strip():
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="token required",
        )
    db = SessionLocal()
    try:
        user = get_current_user(str(token).strip(), db)
        if not user.is_active:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="inactive user",
            )
        return user
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_authenticated(websocket: WebSocket, token: str = Query(...)):
    """اتصال WebSocket با JWT — user_id از توکن استخراج می‌شود."""
    user = _resolve_user_from_ws_token(token)
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
    """مسیر legacy — فقط با token معتبر و user_id هم‌خوان."""
    if token:
        user = _resolve_user_from_ws_token(token)
        if int(user.id) != int(user_id):
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="user mismatch",
            )
    else:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="token required",
        )

    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        manager.disconnect(user_id, websocket)
