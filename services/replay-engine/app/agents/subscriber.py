"""Redis subscriber for prediction_votes / final_decision channels."""

import json
import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.agents.agent_manager import AgentManager

logger = logging.getLogger("replay-engine.subscriber")

# Expected message format:
# {
#   "agent_id": "rl-agent-1",
#   "action": "LONG" | "SHORT" | "CLOSE",
#   "confidence": 0.85,
#   "volume": 3,
#   "timestamp": "2025-01-01T09:15:00",
#   "reason": "Bullish momentum detected"
# }


class PredictionSubscriber:
    """Subscribes to Redis prediction channels and routes orders to agents."""

    def __init__(
        self,
        agent_mgr: AgentManager,
        channels: Optional[list] = None,
    ):
        self._agent_mgr = agent_mgr
        self._channels = channels or ["prediction_votes", "final_decision"]
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "messages_received": 0,
            "orders_placed": 0,
            "orders_rejected": 0,
            "errors": 0,
        }

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    async def start(self, redis_client: aioredis.Redis):
        """Start listening to prediction channels."""
        self._running = True
        self._redis = redis_client
        self._task = asyncio.create_task(self._listen())
        logger.info("PredictionSubscriber started on channels: %s", self._channels)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PredictionSubscriber stopped. Stats: %s", self._stats)

    async def _listen(self):
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(*self._channels)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await self._process_prediction(data, message.get("channel", ""))
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON on prediction channel")
                    self._stats["errors"] += 1
                except Exception as e:
                    logger.error("Prediction processing error: %s", e)
                    self._stats["errors"] += 1
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(*self._channels)
            await pubsub.close()

    async def _process_prediction(self, data: dict, channel: str):
        """Process a single prediction message."""
        self._stats["messages_received"] += 1

        agent_id = data.get("agent_id")
        action = data.get("action", "").upper()
        confidence = float(data.get("confidence", 0))
        volume = int(data.get("volume", 1))

        if not agent_id or not action:
            logger.debug("Skipping prediction: missing agent_id or action")
            self._stats["orders_rejected"] += 1
            return

        config = self._agent_mgr.get_agent_config(agent_id)
        if config is None:
            logger.debug("Skipping prediction from unregistered agent '%s'", agent_id)
            self._stats["orders_rejected"] += 1
            return

        if not config.enabled:
            self._stats["orders_rejected"] += 1
            return

        # Check confidence threshold
        if confidence < config.confidence_threshold:
            logger.debug(
                "Agent '%s' confidence %.2f < threshold %.2f — skipping",
                agent_id, confidence, config.confidence_threshold,
            )
            self._stats["orders_rejected"] += 1
            return

        # Handle CLOSE action
        if action == "CLOSE":
            engine = self._agent_mgr.get_agent_engine(agent_id)
            if engine and engine.active_position:
                try:
                    engine.close_position()
                    self._stats["orders_placed"] += 1
                    logger.info("Agent '%s' CLOSE via prediction (conf=%.2f)", agent_id, confidence)
                except Exception as e:
                    logger.error("Agent '%s' close failed: %s", agent_id, e)
                    self._stats["errors"] += 1
            return

        # LONG or SHORT
        if action not in ("LONG", "SHORT"):
            self._stats["orders_rejected"] += 1
            return

        try:
            result = self._agent_mgr.place_agent_order(agent_id, action, volume)
            self._stats["orders_placed"] += 1
            logger.info(
                "Agent '%s' %s x%d via prediction (conf=%.2f) → %s",
                agent_id, action, volume, confidence, result.get("action"),
            )
        except Exception as e:
            logger.warning("Agent '%s' order rejected: %s", agent_id, e)
            self._stats["orders_rejected"] += 1

    def process_prediction_sync(self, data: dict) -> dict:
        """Synchronous prediction processing (for testing without Redis)."""
        self._stats["messages_received"] += 1

        agent_id = data.get("agent_id")
        action = data.get("action", "").upper()
        confidence = float(data.get("confidence", 0))
        volume = int(data.get("volume", 1))

        if not agent_id or not action:
            self._stats["orders_rejected"] += 1
            return {"status": "rejected", "reason": "missing fields"}

        config = self._agent_mgr.get_agent_config(agent_id)
        if config is None:
            self._stats["orders_rejected"] += 1
            return {"status": "rejected", "reason": "unregistered agent"}

        if not config.enabled:
            self._stats["orders_rejected"] += 1
            return {"status": "rejected", "reason": "agent disabled"}

        if confidence < config.confidence_threshold:
            self._stats["orders_rejected"] += 1
            return {"status": "rejected", "reason": "low confidence"}

        if action == "CLOSE":
            engine = self._agent_mgr.get_agent_engine(agent_id)
            if engine and engine.active_position:
                result = engine.close_position()
                self._stats["orders_placed"] += 1
                return {"status": "ok", "result": result}
            return {"status": "rejected", "reason": "no position"}

        if action not in ("LONG", "SHORT"):
            self._stats["orders_rejected"] += 1
            return {"status": "rejected", "reason": "invalid action"}

        try:
            result = self._agent_mgr.place_agent_order(agent_id, action, volume)
            self._stats["orders_placed"] += 1
            return {"status": "ok", "result": result}
        except Exception as e:
            self._stats["orders_rejected"] += 1
            return {"status": "rejected", "reason": str(e)}
