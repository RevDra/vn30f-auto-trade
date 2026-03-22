import asyncio
import json
import logging
from datetime import datetime

import redis.asyncio as redis
from shared.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_service")

async def test_pubsub():
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )

    pubsub = client.pubsub()
    await pubsub.subscribe("prediction_votes")
    logger.info("Subscribed to prediction_votes")

    # Send mock data
    mock_data = {
        "time": datetime.utcnow().isoformat(),
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000
    }

    # We send enough mock data so that QuantAgent gets enough candles (at least macd_slow=26 for real signals, but minimum 5 required to predict anything according to our main.py logic `if df.empty or len(df) < 5: return`)

    # We first listen for the subscription confirmation message
    msg = await pubsub.get_message(ignore_subscribe_messages=False, timeout=1.0)
    logger.info(f"Sub message: {msg}")

    for _ in range(6):
        await client.publish("market_data_vn30f1m", json.dumps(mock_data))
        await asyncio.sleep(0.1)

    logger.info("Published mock market data to market_data_vn30f1m")

    # Wait for response
    try:
        async with asyncio.timeout(10.0):
            async for message in pubsub.listen():
                if message["type"] == "subscribe": continue
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    logger.info(f"Received prediction vote: {data}")
                    assert data["symbol"] == "VN30F1M"
                    assert "quant_signal" in data
                    assert "regime_state" in data
                    break
    except asyncio.TimeoutError:
        logger.error("Timed out waiting for prediction_votes")
        raise
    finally:
        await pubsub.unsubscribe("prediction_votes")
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_pubsub())
