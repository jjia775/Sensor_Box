import asyncio
from typing import Set
from fastapi import WebSocket

class Broadcaster:
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.clients.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self.clients.discard(ws)

    async def broadcast_json(self, payload: dict):
        stale = []
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)

broadcaster = Broadcaster()
