import json
import logging
import asyncio
import os
import joblib
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

import numpy as np
import pandas as pd
import ta
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
    """Agent to calculate technical features and generate an ensemble trading signal."""

    def __init__(self, models_path: str = "shared/models"):
        self.models_path = models_path
        self.lgbm_model = None
        self.rf_model = None
        self.logres_model = None
        self.scaler = None
        self._load_models()
        logger.info("Initialized QuantAgent with Ensemble Models")

    def _load_models(self):
        """Load trained models and scaler from joblib files."""
        try:
            lgbm_file = os.path.join(self.models_path, "lgbm_quant.joblib")
            rf_file = os.path.join(self.models_path, "rf_quant.joblib")
            logres_file = os.path.join(self.models_path, "logres_quant.joblib")
            scaler_file = os.path.join(self.models_path, "scaler.joblib")

            if all(os.path.exists(f) for f in [lgbm_file, rf_file, logres_file, scaler_file]):
                self.lgbm_model = joblib.load(lgbm_file)
                self.rf_model = joblib.load(rf_file)
                self.logres_model = joblib.load(logres_file)
                self.scaler = joblib.load(scaler_file)
                logger.info("Successfully loaded all quant models and scaler.")
            else:
                logger.error(f"One or more model files not found in {self.models_path}")
        except Exception as e:
            logger.error(f"Error loading models: {e}")

    def _calculate_features(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate technical indicators for the latest row."""
        try:
            if len(df) < 30: # Minimum rows needed for indicators
                return None

            # Create a copy to avoid modifying the original buffer
            df_feat = df.copy()

            # RSI
            df_feat['rsi_14'] = ta.momentum.RSIIndicator(close=df_feat['close'], window=14).rsi()

            # MACD
            macd = ta.trend.MACD(close=df_feat['close'])
            df_feat['macd'] = macd.macd()
            df_feat['macd_signal'] = macd.macd_signal()
            df_feat['macd_diff'] = macd.macd_diff()

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(close=df_feat['close'], window=20, window_dev=2)
            df_feat['bb_mavg'] = bb.bollinger_mavg()
            df_feat['bb_high'] = bb.bollinger_hband()
            df_feat['bb_low'] = bb.bollinger_lband()

            # VWAP
            df_feat['vwap'] = ta.volume.VolumeWeightedAveragePrice(
                high=df_feat['high'], low=df_feat['low'], close=df_feat['close'], volume=df_feat['volume']
            ).volume_weighted_average_price()

            # Select features in the correct order as used during training
            features = [
                'open', 'high', 'low', 'close', 'volume',
                'rsi_14', 'macd', 'macd_signal', 'macd_diff',
                'bb_mavg', 'bb_high', 'bb_low', 'vwap'
            ]

            # Get only the latest row and required features
            latest_features = df_feat[features].tail(1)

            if latest_features.isnull().values.any():
                return None

            return latest_features
        except Exception as e:
            logger.error(f"Error calculating features: {e}")
            return None

    def generate_signal(self, data: pd.DataFrame) -> Tuple[str, float]:
        """
        Generate a trading signal (LONG, SHORT, HOLD) and a confidence score.
        Uses Soft Voting ensemble of LGBM, RF, and LogReg.
        """
        if self.lgbm_model is None or self.rf_model is None or self.logres_model is None:
            logger.warning("Models not loaded, returning HOLD")
            return "HOLD", 0.0

        latest_X = self._calculate_features(data)
        if latest_X is None:
            return "HOLD", 0.0

        try:
            # Get predict_proba from each model
            # LGBM & RF take raw features
            prob_lgbm = self.lgbm_model.predict_proba(latest_X)[0]
            prob_rf = self.rf_model.predict_proba(latest_X)[0]

            # LogReg takes scaled features
            latest_X_scaled = self.scaler.transform(latest_X)
            prob_logres = self.logres_model.predict_proba(latest_X_scaled)[0]

            # Soft Voting: Average probabilities
            # Classes are usually [-1, 0, 1] or [0, 1, 2] depending on how they were encoded
            # Let's check model classes
            classes = self.lgbm_model.classes_ # e.g., [-1, 0, 1]
            avg_probs = (prob_lgbm + prob_rf + prob_logres) / 3.0

            # Find label with highest probability
            best_idx = np.argmax(avg_probs)
            best_label = classes[best_idx]
            confidence = avg_probs[best_idx]

            # Map label to Signal
            signal_map = {1: "LONG", -1: "SHORT", 0: "HOLD"}
            signal = signal_map.get(best_label, "HOLD")

            return signal, float(round(confidence, 4))

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
        import random
        try:
            if len(data) < 20:
                return "Mean-Reverting", 1.0

            close_prices = data['close']
            returns = close_prices.pct_change().dropna()

            if len(returns) == 0:
                return "Mean-Reverting", 1.0

            volatility = returns.std() * np.sqrt(252 * 24 * 12) # Annualized vol approx (5m interval)
            mean_return = returns.mean()

            # Simple heuristic
            if volatility > 0.02:
                state_label = "Volatile"
            elif mean_return > 0.0001:
                state_label = "Trending Up"
            elif mean_return < -0.0001:
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
        if df.empty or len(df) < 5:
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
    logger.info("Starting Quant & Regime Service")
    await service.start()
    yield
    logger.info("Shutting down Quant & Regime Service")
    await service.stop()

# Initialize FastAPI app
app = FastAPI(
    title="Quant & Regime Service",
    description="AI Trading System - Quant Agent and Ensemble Model Service",
    version="1.1.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "buffer_size": len(service.buffer.get_data()),
        "redis_connected": service.redis_client is not None,
        "models_loaded": service.quant_agent.lgbm_model is not None
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
