"""Redis Pub/Sub → WebSocket bridge.

Subscribes to replay-engine channels and broadcasts to dashboard WS clients.
"""

import json
import asyncio
import logging
from typing import Optional, List

import redis.asyncio as aioredis

from backend.ws_manager import WSManager

logger = logging.getLogger("dashboard")

DEFAULT_CHANNELS = ["market_data_vn30f1m", "engine_updates"]


class RedisBridge:
    """Bridges Redis Pub/Sub messages to WebSocket clients."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ws_manager: WSManager,
        channels: Optional[List[str]] = None,
    ):
        self.redis = redis_client
        self.ws = ws_manager
        self.channels = channels or DEFAULT_CHANNELS
        self._running = False
        self._pubsub: Optional[aioredis.client.PubSub] = None

    async def start(self):
        """Start subscribing and bridging."""
        self._running = True
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(*self.channels)
        logger.info(f"Redis bridge subscribed to: {self.channels}")

        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break
                if message["type"] != "message":
                    continue
                try:
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    raw = message["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode()

                    data = json.loads(raw)
                    await self.ws.broadcast(
                        {"channel": channel, "data": data},
                        throttle=(channel == "market_data_vn30f1m"),
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON message on {message.get('channel')}")
                except Exception as e:
                    logger.error(f"Bridge error: {e}")
        except asyncio.CancelledError:
            logger.info("Redis bridge cancelled")
        except Exception as e:
            logger.error(f"Redis bridge fatal: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the bridge gracefully."""
        self._running = False
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(*self.channels)
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

    @property
    def is_running(self) -> bool:
        return self._running
