from app.core.websocket_manager import manager
import asyncio


async def on_workflow_event(event):
    user_id = event["user_id"]

    message = {
        "type": "workflow",
        "event": event["type"],
        "ref_id": event["instance_id"],
    }

    asyncio.create_task(manager.send_to_user(user_id, message))
