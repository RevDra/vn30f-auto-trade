"""WebSocket connection manager — broadcasts messages to all connected clients."""

import asyncio
import logging
import json
import time
from typing import Set, Any
from fastapi import WebSocket

logger = logging.getLogger("dashboard")


class WSManager:
    """Manages WebSocket connections with broadcast + throttling."""

    def __init__(self, max_rate: float = 10.0):
        """
        Args:
            max_rate: Max messages per second per broadcast channel.
        """
        self._connections: Set[WebSocket] = set()
        self._min_interval = 1.0 / max_rate if max_rate > 0 else 0
        self._last_broadcast: float = 0.0
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        logger.info(f"WS connected. Total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)
        logger.info(f"WS disconnected. Total: {len(self._connections)}")

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, data: Any, throttle: bool = True):
        """Send data to all connected clients.

        Args:
            data: Dict or string to send as JSON.
            throttle: If True, rate-limit broadcasts.
        """
        if throttle:
            now = time.monotonic()
            if now - self._last_broadcast < self._min_interval:
                return
            self._last_broadcast = now

        if not self._connections:
            return

        message = json.dumps(data) if isinstance(data, dict) else str(data)
        dead: list = []

        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._connections.discard(ws)

    async def send_to(self, ws: WebSocket, data: Any):
        """Send to a specific client."""
        message = json.dumps(data) if isinstance(data, dict) else str(data)
        try:
            await ws.send_text(message)
        except Exception:
            self._connections.discard(ws)
