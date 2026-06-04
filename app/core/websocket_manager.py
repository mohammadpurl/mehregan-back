class ConnectionManager:

    def __init__(self):
        self.active_connections = {}

    async def connect(self, user_id: int, websocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int, websocket=None):
        ws = self.active_connections.get(user_id)
        if ws and (websocket is None or ws is websocket):
            self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.active_connections.pop(user_id, None)

    async def broadcast(self, message: dict):
        stale_users = []
        for uid, ws in self.active_connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                stale_users.append(uid)
        for uid in stale_users:
            self.active_connections.pop(uid, None)


manager = ConnectionManager()
