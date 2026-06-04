from app.core.websocket_manager import manager
from app.gateways.event_router import route_event


class EventGateway:

    async def dispatch(self, event: str, payload: dict):

        # 1. route event → UI message
        message = route_event(event, payload)

        # 2. user-based delivery
        user_id = message.get("user_id")

        if user_id:
            await manager.send_to_user(user_id, message)

        # 3. broadcast if needed
        elif message.get("broadcast"):
            await manager.broadcast(message)
