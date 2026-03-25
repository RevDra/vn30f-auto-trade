import os
import joblib
import numpy as np
import pandas as pd
import ta
from vnstock import Vnstock
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import precision_score
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("train_quant_models")

# Define target paths
MODELS_DIR = "shared/models"
os.makedirs(MODELS_DIR, exist_ok=True)

def fetch_data():
    """Fetch real data from vnstock or generate synthetic data as fallback."""
    try:
        logger.info("Attempting to fetch real data using vnstock...")
        end_date = pd.Timestamp.today().strftime('%Y-%m-%d')
        start_date = (pd.Timestamp.today() - pd.DateOffset(months=6)).strftime('%Y-%m-%d')
        stock = Vnstock().stock(symbol='VN30F1M', source='VCI')
        df = stock.quote.history(start=start_date, end=end_date, interval='5m')

        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        elif 'tradingDate' in df.columns:
            df['tradingDate'] = pd.to_datetime(df['tradingDate'])
            df.set_index('tradingDate', inplace=True)

        df.columns = [c.lower() for c in df.columns]
        logger.info(f"Successfully fetched real data: {df.shape}")
        return df
    except Exception as e:
        logger.error(f"Failed to fetch real data: {e}")
        logger.info("Generating synthetic Random Walk OHLCV data instead...")
        np.random.seed(42)
        periods = 5000
        dates = pd.date_range(start='2025-01-01', periods=periods, freq='5min')

        # Random walk
        price_changes = np.random.normal(0, 1.5, periods)
        close = 1200 + np.cumsum(price_changes)

        df = pd.DataFrame({
            'open': close + np.random.uniform(-0.5, 0.5, periods),
            'high': close + np.random.uniform(0, 2.0, periods),
            'low': close - np.random.uniform(0, 2.0, periods),
            'close': close,
            'volume': np.random.randint(100, 5000, periods)
        }, index=dates)
        logger.info(f"Generated synthetic data: {df.shape}")
        return df

def calculate_features(df):
    """Calculate technical indicators."""
    df = df.copy()
    df['rsi_14'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

    macd = ta.trend.MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()

    bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_mavg'] = bb.bollinger_mavg()
    df['bb_high'] = bb.bollinger_hband()
    df['bb_low'] = bb.bollinger_lband()

    df['vwap'] = ta.volume.VolumeWeightedAveragePrice(
        high=df['high'], low=df['low'], close=df['close'], volume=df['volume']
    ).volume_weighted_average_price()

    df.dropna(inplace=True)
    return df

def assign_labels(df, threshold=1.0):
    """Generate labels based on price changes."""
    df = df.copy()
    df['next_close'] = df['close'].shift(-1)
    df['price_change'] = df['next_close'] - df['close']
    df.dropna(inplace=True)

    def assign_label(change):
        if change > threshold:
            return 1 # LONG
        elif change < -threshold:
            return -1 # SHORT
        else:
            return 0 # HOLD

    df['target'] = df['price_change'].apply(assign_label)
    return df

def train_and_save_models():
    # 1. Prepare Data
    df = fetch_data()
    df = calculate_features(df)
    df = assign_labels(df)

    features = [
        'open', 'high', 'low', 'close', 'volume',
        'rsi_14', 'macd', 'macd_signal', 'macd_diff',
        'bb_mavg', 'bb_high', 'bb_low', 'vwap'
    ]
    X = df[features]
    y = df['target']

    # 2. Initialize Models with optimized parameters
    lgbm_params = {
        'num_leaves': 29,
        'learning_rate': 0.0139,
        'max_depth': 7,
        'min_child_samples': 27,
        'random_state': 42,
        'verbose': -1
    }
    lgbm_model = LGBMClassifier(**lgbm_params)

    rf_params = {
        'n_estimators': 158,
        'max_depth': 8,
        'min_samples_split': 7,
        'random_state': 42,
        'n_jobs': -1
    }
    rf_model = RandomForestClassifier(**rf_params)

    logres_params = {
        'max_iter': 1000,
        'random_state': 42
    }
    logres_model = LogisticRegression(**logres_params)

    # 3. Fit Models
    logger.info("Training LightGBM model...")
    lgbm_model.fit(X, y)

    logger.info("Training RandomForest model...")
    rf_model.fit(X, y)

    logger.info("Training LogisticRegression model...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    logres_model.fit(X_scaled, y)

    # 4. Save Models and Scaler
    joblib.dump(lgbm_model, os.path.join(MODELS_DIR, "lgbm_quant.joblib"))
    joblib.dump(rf_model, os.path.join(MODELS_DIR, "rf_quant.joblib"))
    joblib.dump(logres_model, os.path.join(MODELS_DIR, "logres_quant.joblib"))
    joblib.dump(scaler, os.path.join(MODELS_DIR, "scaler.joblib"))

    logger.info(f"All models and scaler saved to {MODELS_DIR}")

if __name__ == "__main__":
    train_and_save_models()
