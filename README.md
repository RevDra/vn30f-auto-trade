# 📈 VN30F-AUTO-TRADE: Risk-Aware XAI Trading Monorepo

![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)
![Architecture](https://img.shields.io/badge/Architecture-Microservices-orange)
![Latency](https://img.shields.io/badge/Latency-%3C200ms-brightgreen)

> An enterprise-grade, multi-agent automated trading system designed specifically for the Vietnamese Derivative Market (VN30F1M).

This project aims to tame the high volatility of the VN30F1M via a **Risk-Aware Multi-Agent Architecture**. Instead of relying on a single "black-box" model, the system leverages a committee of specialized AI agents governed by a strict XAI (Explainable AI) Adjudicator to ensure mathematical rigor and absolute risk control.

## 🧠 Core Architecture (The Multi-Agent Committee)

Our prediction layer evaluates market conditions every 5 minutes using a consensus mechanism:

* **Quant Agent (The Aggressor & The Stabilizer):** A low-latency Ensemble of LightGBM, Random Forest, and Logistic Regression evaluating real-time Technical Analysis (TA) indicators.
* **Market Regime Agent (The Context):** A Gaussian Hidden Markov Model (HMM) running in the background to classify the market into 4 latent states (Trending Up, Trending Down, Mean-Reverting, Volatile), dynamically adjusting the risk multiplier.
* **Trading Agent (The Trigger):** A Deep Reinforcement Learning (PPO) model exported to ONNX for lightning-fast inference. It learns to maximize PnL while being penalized for reckless behavior.
* **The Adjudicator (The Gatekeeper):** The ultimate authority. It calculates real-time Historical Simulation VaR (Value at Risk). If any agent proposes an action that breaches the dynamically adjusted VaR threshold, the Adjudicator **Vetoes** the order and logs a transparent JSON explanation (XAI).

## 🛡️ Fail-Safe & Stress Testing

We don't trust backtests without friction. This monorepo includes a heavily engineered **Replay Engine** designed to break the models before the market does:
* **Slippage Injection:** Every paper-trade order suffers a random 2-3 tick slippage (0.2 - 0.3 VN30 points) to simulate real-world liquidity execution.
* **Roll-over Gap Simulation:** Injects 10-15 point gaps on the Friday morning following the expiration Thursday to stress-test maximum drawdown survivability.
* **Graceful Degradation:** Redis Pub/Sub architecture ensures that if the Broker API disconnects, the Execution Service triggers an Emergency Flat protocol.

## 🚀 Quick Start (Local Docker Environment)

The entire microservices ecosystem (Data Feed, Redis, MySQL, Replay Engine, and Agents) is containerized for seamless local deployment.

```bash
# Clone the repository
git clone [https://github.com/your-username/vn30f-auto-trade.git](https://github.com/your-username/vn30f-auto-trade.git)
cd vn30f-auto-trade

# Build and spin up the complete infrastructure
docker-compose up --build -d

# Check the status of all microservices
docker-compose ps
```

## 📂 Monorepo Structure

```text
vn30f-auto-trade/
├── docs/                   # Architecture specs (SRS & SDD)
├── shared/                 # Shared Pydantic schemas and config (Python package)
├── services/
│   ├── adjudicator/        # Risk calculation & XAI JSON logger
│   ├── data-feed/          # Ingests vnstock & tvdatafeed (Primary/Fallback)
│   ├── dashboard/          # FastAPI & Websocket real-time monitoring
│   ├── execution/          # Broker API integration (DNSE/SSI)
│   ├── quant-regime/       # LightGBM/RF/LogReg + HMM Inference
│   ├── replay-engine/      # Mock exchange with Slippage & Gap injection
│   └── rl-agent/           # PPO ONNX Inference
├── docker-compose.yml      # Infrastructure orchestration
└── README.md
```

## 📜 License

This project is licensed under the **Apache License 2.0**. See the `LICENSE` file for more details.
