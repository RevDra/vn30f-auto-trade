"""Redis Pub/Sub listener for market data."""

import json
import asyncio
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis

from app.session import SessionManager

logger = logging.getLogger("replay-engine")


async def listen_to_redis(
    redis_client: aioredis.Redis,
    session_mgr: SessionManager,
    channel: str = "market_data_vn30f1m",
):
    """Background task: subscribe to Redis market data and feed ticks to all sessions."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    logger.info(f"Subscribed to Redis channel '{channel}'")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                timestamp = data.get("timestamp", datetime.now().isoformat())
                price = float(data.get("close", 0.0))
                regime = data.get("regime", "unknown")

                if price > 0:
                    session_mgr.broadcast_tick(timestamp, price, regime)

            except Exception as e:
                logger.error(f"Error processing tick: {e}")
    except asyncio.CancelledError:
        logger.info("Redis listener cancelled")
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
