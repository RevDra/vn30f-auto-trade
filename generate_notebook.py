import nbformat as nbf

nb = nbf.v4.new_notebook()

# Title
title_md = """# AI Trading System Phase 2: Quant Models Evaluation
**Objective:** Evaluate default parameters for tree-based models and Logistic Regression for the Soft Voting mechanism of the Quant Agent."""
nb.cells.append(nbf.v4.new_markdown_cell(title_md))

# Imports
imports_code = """import time
import numpy as np
import pandas as pd
from vnstock import Vnstock
import ta
import warnings
warnings.filterwarnings('ignore')

# Models
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression

# Evaluation & Validation
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import precision_score, f1_score, average_precision_score
from sklearn.preprocessing import StandardScaler"""
nb.cells.append(nbf.v4.new_code_cell(imports_code))

# Data Fetching
data_fetching_md = """## 1. Data Preparation
Fetch 5-minute OHLCV historical data for the `VN30F1M` derivative symbol over the last 6 months using `vnstock` with source `'VCI'`."""
nb.cells.append(nbf.v4.new_markdown_cell(data_fetching_md))

data_fetching_code = """# Fetch 6 months of data
end_date = pd.Timestamp.today().strftime('%Y-%m-%d')
start_date = (pd.Timestamp.today() - pd.DateOffset(months=6)).strftime('%Y-%m-%d')

print(f"Fetching data from {start_date} to {end_date}...")

stock = Vnstock().derivative(symbol='VN30F1M', source='VCI')
df = stock.quote.history(start=start_date, end=end_date, resolution='5')

# Memory requirement check: use 'time' or 'tradingDate' column to parse valid datetime
if 'time' in df.columns:
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
elif 'tradingDate' in df.columns:
    df['tradingDate'] = pd.to_datetime(df['tradingDate'])
    df.set_index('tradingDate', inplace=True)

# Rename columns to standard lowercase
df.columns = [c.lower() for c in df.columns]
print(f"Data fetched: {df.shape}")
df.head()"""
nb.cells.append(nbf.v4.new_code_cell(data_fetching_code))

# Feature Engineering
feature_eng_md = """## 2. Feature Engineering
Calculate technical indicators: MACD, RSI(14), VWAP, and Bollinger Bands. Then, drop NaN values."""
nb.cells.append(nbf.v4.new_markdown_cell(feature_eng_md))

feature_eng_code = """# Calculate RSI(14)
df['rsi_14'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

# Calculate MACD
macd = ta.trend.MACD(close=df['close'])
df['macd'] = macd.macd()
df['macd_signal'] = macd.macd_signal()
df['macd_diff'] = macd.macd_diff()

# Calculate Bollinger Bands
bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
df['bb_mavg'] = bb.bollinger_mavg()
df['bb_high'] = bb.bollinger_hband()
df['bb_low'] = bb.bollinger_lband()

# Calculate VWAP
df['vwap'] = ta.volume.VolumeWeightedAveragePrice(
    high=df['high'], low=df['low'], close=df['close'], volume=df['volume']
).volume_weighted_average_price()

# Drop rows with NaN values resulting from indicator lookback periods
df.dropna(inplace=True)
print(f"Data shape after feature engineering and dropping NaNs: {df.shape}")"""
nb.cells.append(nbf.v4.new_code_cell(feature_eng_code))

# Labeling
labeling_md = """## 3. Labeling (Target Variable Generation)
Define 3 classes based on the next 5-minute candle's price change:
- `LONG` (1): Price increases by more than 1.0 point.
- `SHORT` (-1): Price decreases by more than 1.0 point.
- `HOLD` (0): Price changes by 1.0 point or less in either direction."""
nb.cells.append(nbf.v4.new_markdown_cell(labeling_md))

labeling_code = """THRESHOLD = 1.0

# Calculate difference to next candle's close
df['next_close'] = df['close'].shift(-1)
df['price_change'] = df['next_close'] - df['close']

# Drop the last row as we don't know its future
df.dropna(inplace=True)

def assign_label(change):
    if change > THRESHOLD:
        return 1
    elif change < -THRESHOLD:
        return -1
    else:
        return 0

df['target'] = df['price_change'].apply(assign_label)

print("Class distribution:")
print(df['target'].value_counts(normalize=True))"""
nb.cells.append(nbf.v4.new_code_cell(labeling_code))

# Modeling
modeling_md = """## 4. Modeling & Evaluation
Train models using `TimeSeriesSplit` cross-validation with default parameters. Compare their precision, Macro F1-Score, PR-AUC, and Inference Time (ms)."""
nb.cells.append(nbf.v4.new_markdown_cell(modeling_md))

modeling_code = """# Prepare features (X) and target (y)
features = [
    'open', 'high', 'low', 'close', 'volume',
    'rsi_14', 'macd', 'macd_signal', 'macd_diff',
    'bb_mavg', 'bb_high', 'bb_low', 'vwap'
]
X = df[features]
y = df['target']

# Define models with default parameters
models = {
    'LogisticRegression': LogisticRegression(max_iter=1000, random_state=42),
    'RandomForest': RandomForestClassifier(random_state=42),
    'ExtraTrees': ExtraTreesClassifier(random_state=42),
    'LightGBM': LGBMClassifier(random_state=42, verbose=-1),
    'XGBoost': XGBClassifier(random_state=42, use_label_encoder=False, eval_metric='mlogloss'),
    'CatBoost': CatBoostClassifier(random_state=42, verbose=0)
}

# Transform target to [0, 1, 2] since XGBoost expects classes starting from 0
# Original: -1 (SHORT), 0 (HOLD), 1 (LONG)
# Mapped: 0 (SHORT), 1 (HOLD), 2 (LONG)
y_mapped = y.map({-1: 0, 0: 1, 1: 2})

tscv = TimeSeriesSplit(n_splits=5)
results = []

for name, model in models.items():
    print(f"Evaluating {name}...")

    precisions, f1s, praucs, inf_times = [], [], [], []

    for train_index, test_index in tscv.split(X):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y_mapped.iloc[train_index], y_mapped.iloc[test_index]

        # Scaling is needed for LogisticRegression
        if name == 'LogisticRegression':
            scaler = StandardScaler()
            X_train = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
        else:
            X_test_scaled = X_test.values

        model.fit(X_train, y_train)

        # Prediction
        y_pred = model.predict(X_test_scaled)
        y_pred_proba = model.predict_proba(X_test_scaled)

        # In sklearn/xgboost, predict might return 2D array, let's flatten
        if y_pred.ndim > 1:
            y_pred = y_pred.flatten()

        # Metrics
        # average='macro' calculates metrics for each label, and finds their unweighted mean.
        # This does not take label imbalance into account.
        precisions.append(precision_score(y_test, y_pred, average='macro', zero_division=0))
        f1s.append(f1_score(y_test, y_pred, average='macro', zero_division=0))

        # Multi-class PR-AUC (One-vs-Rest)
        try:
            # For PR-AUC, we use average_precision_score with macro average across classes
            # Note: requires scikit-learn >= 0.24 and probabilities
            # Convert y_test to one-hot for PR-AUC
            y_test_dummies = pd.get_dummies(y_test).values

            # Make sure shape matches (sometimes a class might not be present in test set)
            if y_test_dummies.shape[1] == y_pred_proba.shape[1]:
                prauc = average_precision_score(y_test_dummies, y_pred_proba, average='macro')
                praucs.append(prauc)
        except Exception as e:
            pass # Skip if error occurs due to missing classes

        # Inference Time test (1 row)
        single_row = X_test_scaled[[0]]
        start_time = time.perf_counter()
        _ = model.predict(single_row)
        end_time = time.perf_counter()
        inf_times.append((end_time - start_time) * 1000) # Convert to ms

    results.append({
        'Model': name,
        'Precision (Macro)': np.mean(precisions),
        'Macro F1-Score': np.mean(f1s),
        'PR-AUC': np.mean(praucs) if praucs else np.nan,
        'Inference Time (ms)': np.mean(inf_times)
    })

# Display Results
results_df = pd.DataFrame(results).set_index('Model')
results_df.sort_values('Precision (Macro)', ascending=False, inplace=True)
results_df"""
nb.cells.append(nbf.v4.new_code_cell(modeling_code))

# Save notebook
with open('notebooks/quant_model_experiment.ipynb', 'w', encoding='utf-8') as f:
    nbf.write(nb, f)
print("Notebook generated successfully at notebooks/quant_model_experiment.ipynb")
