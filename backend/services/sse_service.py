"""
SSEBroadcaster — singleton that manages all connected SSE clients.

Each client connection gets its own asyncio.Queue.
Any router can call `broadcaster.broadcast(event, data)` to push
a named SSE event to every connected browser tab instantly.
"""
import asyncio
import json
from typing import Any


class SSEBroadcaster:
    def __init__(self):
        self._clients: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._clients.remove(q)
        except ValueError:
            pass

    async def broadcast(self, event: str, data: Any) -> None:
        """Push a named SSE event to all connected clients."""
        if not self._clients:
            return
        message = json.dumps(data)
        for q in list(self._clients):
            await q.put((event, message))

    @property
    def client_count(self) -> int:
        return len(self._clients)


# Single shared instance used across all routers
broadcaster = SSEBroadcaster()
