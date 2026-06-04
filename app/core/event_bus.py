from collections import defaultdict
from typing import Callable, List
import asyncio


class EventBus:

    def __init__(self):
        self.subscribers = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable):
        self.subscribers[event_name].append(handler)

    async def publish(self, event_name: str, payload: dict):
        handlers = self.subscribers.get(event_name, [])

        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(payload)
            else:
                handler(payload)


event_bus = EventBus()
