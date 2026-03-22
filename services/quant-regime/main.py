import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI
import uvicorn
import redis.asyncio as redis
from hmmlearn.hmm import GaussianHMM

from shared.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("quant-regime")

class DataBuffer:
    """Buffer to hold a maximum of 100 recent candles as a pandas DataFrame."""
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.data: pd.DataFrame = pd.DataFrame()
        logger.info(f"Initialized DataBuffer with max_size={max_size}")

    def add_candle(self, candle_data: Dict[str, Any]) -> None:
        """Add a new candle to the buffer."""
        try:
            # Expected format: {'time': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
            # Add to dataframe
            new_row = pd.DataFrame([candle_data])
            if 'time' in new_row.columns:
                new_row['time'] = pd.to_datetime(new_row['time'])
                new_row.set_index('time', inplace=True)

            if self.data.empty:
                self.data = new_row
            else:
                self.data = pd.concat([self.data, new_row])

            # Keep only the last `max_size` rows
            if len(self.data) > self.max_size:
                self.data = self.data.iloc[-self.max_size:]

        except Exception as e:
            logger.error(f"Error adding candle to buffer: {e}")

    def get_data(self) -> pd.DataFrame:
        """Get the current data buffer."""
        return self.data.copy()

class QuantAgent:
    """Agent to calculate MACD and RSI and generate a trading signal."""

    def __init__(self, rsi_period: int = 14, macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9):
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        logger.info("Initialized QuantAgent")

    def _calculate_rsi(self, series: pd.Series) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_macd(self, series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD, Signal, and Histogram."""
        exp1 = series.ewm(span=self.macd_fast, adjust=False).mean()
        exp2 = series.ewm(span=self.macd_slow, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd - signal
        return macd, signal, histogram

    def generate_signal(self, data: pd.DataFrame) -> Tuple[str, float]:
        """
        Generate a trading signal (LONG, SHORT, HOLD) and a confidence score (0.0 to 1.0).
        Returns: (signal, confidence)
        """
        if len(data) < self.macd_slow:
            return "HOLD", 0.0

        try:
            close_prices = data['close']

            # Calculate indicators
            rsi = self._calculate_rsi(close_prices)
            macd, signal, hist = self._calculate_macd(close_prices)

            # Get latest values
            current_rsi = rsi.iloc[-1]
            current_macd = macd.iloc[-1]
            current_signal = signal.iloc[-1]

            # Simple logic for signals
            # Note: In a real system this would be more sophisticated
            action = "HOLD"
            confidence = 0.5

            if pd.isna(current_rsi) or pd.isna(current_macd):
                return "HOLD", 0.0

            if current_rsi < 30 and current_macd > current_signal:
                action = "LONG"
                confidence = min(1.0, (30 - current_rsi) / 30 + 0.5)
            elif current_rsi > 70 and current_macd < current_signal:
                action = "SHORT"
                confidence = min(1.0, (current_rsi - 70) / 30 + 0.5)
            elif current_macd > current_signal:
                action = "LONG"
                confidence = 0.6
            elif current_macd < current_signal:
                action = "SHORT"
                confidence = 0.6

            return action, round(confidence, 2)

        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return "HOLD", 0.0

class RegimeModel:
    """Hidden Markov Model for detecting market regimes."""

    def __init__(self, n_components: int = 4):
        self.n_components = n_components
        self.model = GaussianHMM(n_components=n_components, covariance_type="full", n_iter=100)
        self.is_trained = False

        # Mapping from integer state to string label
        self.state_labels = {
            0: "Trending Up",
            1: "Trending Down",
            2: "Mean-Reverting",
            3: "Volatile"
        }

        # Mapping from state to regime multiplier for risk
        self.regime_multipliers = {
            "Trending Up": 1.0,
            "Trending Down": 1.0,
            "Mean-Reverting": 1.0,
            "Volatile": 0.8
        }
        logger.info(f"Initialized RegimeModel with {n_components} components.")

    def predict_regime(self, data: pd.DataFrame) -> Tuple[str, float]:
        """
        Predict the current market regime based on the data.
        Returns: (regime_label, regime_multiplier)
        """
        # Per requirements, if not trained, return random regime or simple calculation
        # "Chưa cần thiết lập cronjob retrain HMM ở bước này"
        import random
        try:
            # We don't train here. Since we're not training, we mock the prediction
            # based on simple volatility

            if len(data) < 20:
                # Return default if not enough data
                return "Mean-Reverting", 1.0

            # Very simple logic to mock HMM states without actual training
            close_prices = data['close']
            returns = close_prices.pct_change().dropna()

            if len(returns) == 0:
                return "Mean-Reverting", 1.0

            volatility = returns.std() * np.sqrt(252 * 24 * 60 / 5) # Annualized vol approx
            mean_return = returns.mean()

            # Simple heuristic
            if volatility > 0.02: # arbitrarily high threshold for volatility
                state_label = "Volatile"
            elif mean_return > 0.001:
                state_label = "Trending Up"
            elif mean_return < -0.001:
                state_label = "Trending Down"
            else:
                state_label = "Mean-Reverting"

            multiplier = self.regime_multipliers.get(state_label, 1.0)
            return state_label, multiplier

        except Exception as e:
            logger.error(f"Error predicting regime: {e}")
            return "Mean-Reverting", 1.0

class QuantRegimeService:
    """Main service logic handling Redis pub/sub and agents."""

    def __init__(self):
        self.buffer = DataBuffer(max_size=100)
        self.quant_agent = QuantAgent()
        self.regime_model = RegimeModel(n_components=4)
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def connect_redis(self):
        """Connect to Redis."""
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True
            )
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe("market_data_vn30f1m")
            logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT} and subscribed to market_data_vn30f1m")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def process_messages(self):
        """Listen to Redis channel and process new market data."""
        if not self.pubsub:
            logger.error("Redis PubSub not initialized")
            return

        self.running = True
        logger.info("Started processing messages from Redis")

        try:
            async for message in self.pubsub.listen():
                if not self.running:
                    break

                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        # Check if this is candle data (has required OHLCV fields)
                        if all(k in data for k in ["time", "open", "high", "low", "close", "volume"]):
                            self.buffer.add_candle(data)
                            await self._analyze_and_publish()
                        else:
                            logger.warning(f"Received malformed data: {data}")
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode JSON from message: {message['data']}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
        except asyncio.CancelledError:
            logger.info("Message processing task cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in message loop: {e}")
        finally:
            self.running = False

    async def _analyze_and_publish(self):
        """Run agents on current buffer and publish the combined signal."""
        df = self.buffer.get_data()
        if df.empty or len(df) < 5:  # Need minimum data to do anything
            return

        try:
            # 1. Quant Agent
            signal, confidence = self.quant_agent.generate_signal(df)

            # 2. Regime Agent (HMM)
            regime_state, multiplier = self.regime_model.predict_regime(df)

            # 3. Combine to JSON
            vote_payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": "VN30F1M",
                "quant_signal": signal,
                "quant_confidence": confidence,
                "regime_state": regime_state,
                "regime_multiplier": multiplier,
                "source": "quant-regime"
            }

            # 4. Publish to prediction_votes channel
            if self.redis_client:
                await self.redis_client.publish(
                    "prediction_votes",
                    json.dumps(vote_payload)
                )
                logger.info(f"Published prediction vote: {vote_payload}")

        except Exception as e:
            logger.error(f"Error during analysis and publishing: {e}")

    async def start(self):
        """Start the service."""
        await self.connect_redis()
        self.task = asyncio.create_task(self.process_messages())

    async def stop(self):
        """Stop the service gracefully."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.unsubscribe("market_data_vn30f1m")
            await self.pubsub.close()

        if self.redis_client:
            await self.redis_client.close()

        logger.info("Service stopped gracefully")

# Global service instance
service = QuantRegimeService()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage FastAPI application lifecycle."""
    # Startup
    logger.info("Starting Quant & Regime Service")
    await service.start()
    yield
    # Shutdown
    logger.info("Shutting down Quant & Regime Service")
    await service.stop()

# Initialize FastAPI app
app = FastAPI(
    title="Quant & Regime Service",
    description="AI Trading System - Quant Agent and HMM Regime Service",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "buffer_size": len(service.buffer.get_data()),
        "redis_connected": service.redis_client is not None
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
