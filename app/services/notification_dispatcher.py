from app.core.websocket_manager import manager


async def dispatch_notification(user_id: int, payload: dict):
    """
    فقط مسئول ارسال real-time
    """
    await manager.send_to_user(user_id, payload)
