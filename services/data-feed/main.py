import asyncio
import json
import logging
import traceback
import sys
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel
from fastapi import FastAPI
import redis

# Make sure we can import from shared
sys.path.append("/app")
from shared.config import settings

# Try importing data libraries
try:
    from vnstock import Vnstock
except ImportError:
    Vnstock = None

try:
    from tvDatafeed import TvDatafeed, Interval
except ImportError:
    TvDatafeed = None
    Interval = None

from contextlib import asynccontextmanager

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("data-feed")

# Initialize global dependencies
redis_client = None
fetcher = None
background_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, fetcher, background_tasks

    # Initialize Fetcher
    fetcher = DataFetcher()

    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
        redis_client.ping()
        logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None

    # Start the background task
    task = asyncio.create_task(data_fetch_loop())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    yield

    # Cleanup
    for task in background_tasks:
        task.cancel()
    if redis_client:
        redis_client.close()


app = FastAPI(title="Data Feed Service", version="1.0.0", lifespan=lifespan)

class OHLCVData(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str

class DataFetcher:
    """
    Data fetching class with primary and fallback sources.
    Includes data cleansing and cross-checking logic.
    """
    def __init__(self, symbol: str = "VN30F1M"):
        self.symbol = symbol
        # Initialize libraries inside a try-except to avoid crashing on start if not configured
        try:
            self.tv = TvDatafeed() if TvDatafeed else None
        except Exception as e:
            logger.error(f"Error initializing tvDatafeed: {e}")
            self.tv = None

        try:
            self.vnstock = Vnstock() if Vnstock else None
        except Exception as e:
            logger.error(f"Error initializing Vnstock: {e}")
            self.vnstock = None

    async def fetch_primary(self) -> Optional[Dict[str, Any]]:
        """Fetch data using vnstock (Primary Source)"""
        if not self.vnstock:
            logger.error("vnstock is not installed or initialized.")
            return None

        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                try:
                    # Based on our previous tests, vnstock is a bit flaky with VN30F1M directly
                    # Let's try to get derivative data
                    stock = self.vnstock.stock(symbol=self.symbol, source='VCI')

                    # Fetch latest data for today with 5m interval
                    now = datetime.now()
                    now_str = now.strftime('%Y-%m-%d')

                    df = stock.quote.history(start=now_str, end=now_str, interval='5m')
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]

                        # Extract proper timestamp
                        ts_val = latest.get('time') or latest.get('tradingDate')
                        if ts_val is not None:
                            try:
                                # Try parsing if it's a string, or just use it if it's already a datetime/timestamp object
                                if isinstance(ts_val, str):
                                    # Might be '2026-03-22 14:30:00' or similar
                                    # Fallback to pandas to_datetime which is robust
                                    import pandas as pd
                                    dt_obj = pd.to_datetime(ts_val)
                                    timestamp_str = dt_obj.isoformat()
                                else:
                                    # Assume it's a datetime-like object
                                    timestamp_str = ts_val.isoformat()
                            except Exception:
                                timestamp_str = datetime.now().isoformat()
                        else:
                            timestamp_str = datetime.now().isoformat()

                        return {
                            "timestamp": timestamp_str,
                            "open": float(latest.get('open', 0)),
                            "high": float(latest.get('high', 0)),
                            "low": float(latest.get('low', 0)),
                            "close": float(latest.get('close', 0)),
                            "volume": float(latest.get('volume', 0))
                        }
                    return None
                except Exception as e:
                    logger.error(f"vnstock fetch exception: {e}")
                    return None

            # 10s timeout
            result = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=10.0)
            return result
        except asyncio.TimeoutError:
            logger.warning("Primary source (vnstock) timeout > 10s")
            return None
        except Exception as e:
            logger.error(f"Primary source (vnstock) error: {e}")
            return None

    async def fetch_fallback(self) -> Optional[Dict[str, Any]]:
        """Fetch data using tvdatafeed (Fallback Source)"""
        if not self.tv:
            logger.error("tvdatafeed is not installed or initialized.")
            return None

        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                try:
                    df = self.tv.get_hist(symbol=self.symbol, exchange='HNX', interval=Interval.in_5_minute, n_bars=1)
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        return {
                            "timestamp": str(latest.name),
                            "open": float(latest['open']),
                            "high": float(latest['high']),
                            "low": float(latest['low']),
                            "close": float(latest['close']),
                            "volume": float(latest['volume'])
                        }
                    return None
                except Exception as e:
                    logger.error(f"tvdatafeed fetch exception: {e}")
                    return None

            # Fallback timeout
            result = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=10.0)
            return result
        except asyncio.TimeoutError:
            logger.warning("Fallback source (tvdatafeed) timeout > 10s")
            return None
        except Exception as e:
            logger.error(f"Fallback source (tvdatafeed) error: {e}")
            return None

    async def get_cleansed_data(self) -> Optional[OHLCVData]:
        """
        Fetches data from both sources if possible, cross-checks, and returns the best data.
        """
        primary_task = asyncio.create_task(self.fetch_primary())
        fallback_task = asyncio.create_task(self.fetch_fallback())

        results = await asyncio.gather(primary_task, fallback_task, return_exceptions=True)

        primary_data = results[0] if not isinstance(results[0], Exception) else None
        fallback_data = results[1] if not isinstance(results[1], Exception) else None

        if isinstance(results[0], Exception):
            logger.error(f"Primary task raised exception: {results[0]}")

        if isinstance(results[1], Exception):
            logger.error(f"Fallback task raised exception: {results[1]}")

        # Cross-check logic: compare close prices if both returned valid data
        p_close = primary_data.get('close', 0.0) if primary_data else 0.0
        f_close = fallback_data.get('close', 0.0) if fallback_data else 0.0

        if p_close > 0 and f_close > 0:
            diff_pct = abs(p_close - f_close) / p_close
            if diff_pct > 0.001:  # 0.1%
                logger.warning(f"[CROSS-CHECK WARNING] Deviation {diff_pct*100:.3f}% > 0.1% between Primary ({p_close}) and Fallback ({f_close})")

        # Prefer primary, fallback if primary fails
        final_data = None
        source_used = ""

        if primary_data and p_close > 0:
            final_data = primary_data
            source_used = "vnstock"
        elif fallback_data and f_close > 0:
            final_data = fallback_data
            source_used = "tvdatafeed"
        else:
            logger.error("Failed to fetch valid data from both primary and fallback sources.")
            return None

        return OHLCVData(
            timestamp=str(final_data['timestamp']),
            open=float(final_data['open']),
            high=float(final_data['high']),
            low=float(final_data['low']),
            close=float(final_data['close']),
            volume=float(final_data['volume']),
            source=source_used
        )

async def data_fetch_loop():
    """
    Background task that runs every 5 minutes to fetch and publish data.
    Wrapped in a broad try/except to prevent service crash.
    """
    logger.info("Starting Data Fetch Loop (5-minute interval)")

    # We use a 5-minute loop
    while True:
        try:
            logger.info("Fetching latest OHLCV data for VN30F1M...")
            if fetcher:
                data = await fetcher.get_cleansed_data()

                if data:
                    json_data = data.model_dump_json()
                    logger.info(f"Cleansed Data: {json_data}")

                    if redis_client:
                        # Publish to Redis Pub/Sub
                        channel = "market_data_vn30f1m"
                        redis_client.publish(channel, json_data)
                        logger.info(f"Published data to Redis channel '{channel}'")
                    else:
                        logger.warning("Redis client is not connected. Data fetched but not published.")
                else:
                    logger.warning("No data retrieved from fetcher.")
            else:
                logger.error("Data fetcher not initialized.")

        except Exception as e:
            logger.error(f"Unhandled exception in data_fetch_loop: {e}")
            logger.error(traceback.format_exc())

        # Sleep for 5 minutes (300 seconds)
        await asyncio.sleep(300)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "data-feed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
