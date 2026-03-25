import pandas as pd
import numpy as np
from main import QuantAgent
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_quant_agent")

def test_quant_agent():
    # 1. Initialize QuantAgent
    # It should load models from shared/models/ automatically
    # Adjusting path because we run from services/quant-regime
    agent = QuantAgent(models_path="../../shared/models")

    if agent.lgbm_model is None:
        logger.error("Failed to load models. Make sure they are trained and saved in shared/models/")
        return

    # 2. Create mock data (need at least 30 rows for indicators)
    periods = 50
    dates = pd.date_range(start='2025-01-01', periods=periods, freq='5min')
    np.random.seed(42)
    close = 1200 + np.cumsum(np.random.normal(0, 1, periods))

    df = pd.DataFrame({
        'open': close - 0.5,
        'high': close + 1.0,
        'low': close - 1.0,
        'close': close,
        'volume': np.random.randint(100, 1000, periods)
    }, index=dates)

    # 3. Generate Signal
    signal, confidence = agent.generate_signal(df)

    logger.info(f"Generated Signal: {signal}, Confidence: {confidence}")

    # Assertions
    assert signal in ["LONG", "SHORT", "HOLD"]
    assert 0.0 <= confidence <= 1.0
    logger.info("Test passed!")

if __name__ == "__main__":
    test_quant_agent()
