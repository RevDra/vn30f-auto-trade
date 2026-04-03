# VN30F Mock Exchange — Version 1.0 Architecture

## Overview

Mock Exchange cho VN30F Futures — sàn giao dịch mô phỏng hoàn chỉnh với dashboard real-time, persistence layer, và hệ thống agent tournament. Được xây dựng dưới dạng microservice, sử dụng Redis Pub/Sub cho giao tiếp giữa các service.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Network                        │
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐   │
│  │  Redis    │◄──►│  Data Feed   │    │     Replay Engine         │   │
│  │  (Pub/Sub │    │  (Market     │    │  ┌──────────────────────┐ │   │
│  │  + Cache) │    │   Data)      │    │  │ Core Exchange Engine │ │   │
│  └────┬──┬──┘    └──────────────┘    │  │  - FeeCalculator     │ │   │
│       │  │                            │  │  - MarginManager     │ │   │
│       │  │       ┌──────────────┐    │  │  - MetricTracker     │ │   │
│       │  │       │  MySQL 8.0   │◄──►│  │  - SlippageModel     │ │   │
│       │  │       │  (Persist)   │    │  │  - SessionValidator  │ │   │
│       │  │       └──────────────┘    │  └──────────────────────┘ │   │
│       │  │                            │  ┌──────────────────────┐ │   │
│       │  │                            │  │ Persistence Layer    │ │   │
│       │  │                            │  │  - SQLAlchemy Async  │ │   │
│       │  │                            │  │  - AutoSaver         │ │   │
│       │  │                            │  │  - History API       │ │   │
│       │  │                            │  └──────────────────────┘ │   │
│       │  │                            │  ┌──────────────────────┐ │   │
│       │  │                            │  │ Agent System         │ │   │
│       │  │                            │  │  - AgentManager      │ │   │
│       │  │                            │  │  - Tournament        │ │   │
│       │  │                            │  │  - Leaderboard       │ │   │
│       │  │                            │  │  - PredictionSub     │ │   │
│       │  │                            │  └──────────────────────┘ │   │
│       │  │                            └──────────────────────────┘   │
│       │  │                                                           │
│       │  │       ┌──────────────────────────────────────────┐       │
│       │  └──────►│  Dashboard                                │       │
│       │          │  ┌───────────┐    ┌───────────────────┐  │       │
│       └─────────►│  │ Backend   │◄──►│ Frontend (React)  │  │       │
│                  │  │ FastAPI   │    │ Vite + Tailwind   │  │       │
│                  │  │ WebSocket │    │ TradingView Chart │  │       │
│                  │  └───────────┘    └───────────────────┘  │       │
│                  └──────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

## Module Structure

### Replay Engine (`services/replay-engine/`)

```
app/
├── __init__.py
├── constants.py          # VN30F exchange constants (contract multiplier, fees, margins)
├── fees.py               # Multi-layer fee calculator (broker + HNX + VSD + TNCN tax)
├── risk.py               # MarginManager (17% initial, margin call, ±7% price limit)
├── metrics.py            # Win rate, max drawdown, Sharpe ratio, equity curve
├── session_validator.py  # Trading session hours (ATO/CONT1/CONT2/ATC)
├── slippage.py           # Volume-dependent slippage model
├── engine.py             # Core ReplayEngine (order execution, rollover, PnL)
├── session.py            # SessionManager (multi-session, broadcast tick)
├── api.py                # FastAPI 20+ endpoints (orders, sessions, health)
├── listeners.py          # Redis Pub/Sub market data listener
│
├── persistence/          # Phase 3: MySQL persistence
│   ├── database.py       # Async SQLAlchemy engine (MySQL prod, SQLite test)
│   ├── models.py         # ORM: TradingSession, Trade, EquitySnapshot
│   ├── repository.py     # Async CRUD + aggregation queries
│   ├── auto_saver.py     # Background auto-save (trades + equity + metrics)
│   └── history_api.py    # REST: /history/sessions, /trades, /equity-curve, /compare
│
└── agents/               # Phase 4: Agent integration
    ├── agent_manager.py  # Agent registration, isolation, order routing
    ├── subscriber.py     # Redis prediction_votes subscriber
    ├── leaderboard.py    # Multi-metric ranking (PnL, Sharpe, win rate, drawdown)
    ├── tournament.py     # Tournament orchestration (create/start/pause/stop)
    └── agent_api.py      # REST: /agents/*, /tournament/*, /leaderboard/*
```

### Dashboard (`services/dashboard/`)

```
backend/
├── app.py                # FastAPI + WebSocket + REST proxy to replay-engine
├── ws_manager.py         # WebSocket connection manager (broadcast, throttle)
└── redis_bridge.py       # Redis Pub/Sub → WebSocket bridge

frontend/
├── src/
│   ├── App.tsx           # Main layout (12-column CSS grid)
│   ├── components/
│   │   ├── CandlestickChart.tsx  # TradingView Lightweight Charts (live candles)
│   │   ├── EquityMetrics.tsx     # Equity curve + 6 metric cards
│   │   ├── TradePosition.tsx     # Trade history table + position panel
│   │   └── OrderPanel.tsx        # LONG/SHORT/CLOSE buttons + volume stepper
│   ├── hooks/
│   │   ├── useWebSocket.ts       # Auto-reconnecting WebSocket hook
│   │   └── useApi.ts             # REST API hooks with polling
│   └── types/
│       └── api.ts                # TypeScript interfaces for all API responses
├── Dockerfile            # Multi-stage: Node build → nginx serve
└── nginx.conf            # API/WS proxy to dashboard-backend
```

## VN30F Exchange Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Contract Multiplier | 100,000 VND/point | HNX |
| Tick Size | 0.1 points (10,000 VND) | HNX |
| Initial Margin | 17% | VSD (03/2026) |
| Maintenance Margin | 13.6% (80% × initial) | VSD |
| Price Limit | ±7% from reference | HNX |
| Max Contracts (Retail) | 500 | VSD |
| Broker Fee | 2,000 VND/side/contract | VPS default |
| Exchange Fee (HNX) | 2,700 VND/side/contract | HNX |
| Clearing Fee (VSD) | 2,550 VND/side/contract | VSD |
| TNCN Tax | 0.1% on transfer value | MOF |
| Expiry | 3rd Thursday of month | HNX |
| Sessions | ATO 8:45-9:00, CONT1 9:00-11:30, CONT2 13:00-14:30, ATC 14:30-14:45 | HNX |

## API Endpoints

### Core Engine (replay-engine:8001)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (Redis + DB status) |
| GET | `/api/v1/pnl` | Current PnL, balance, equity, active position |
| POST | `/api/v1/order` | Place LONG/SHORT order |
| POST | `/api/v1/close-position` | Close active position |
| GET | `/api/v1/trades` | Paginated trade history |
| GET | `/api/v1/equity-curve` | Equity curve timeseries |
| GET | `/api/v1/sessions` | List all sessions |
| POST | `/api/v1/sessions` | Create new session |
| PUT | `/api/v1/sessions/{id}/activate` | Switch active session |
| DELETE | `/api/v1/sessions/{id}` | Delete session |
| POST | `/api/v1/reset` | Reset engine to initial state |

### History (replay-engine:8001)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/history/sessions` | List persisted sessions (filterable) |
| GET | `/api/v1/history/sessions/{id}` | Session detail + trade stats |
| GET | `/api/v1/history/sessions/{id}/trades` | Paginated trade history (from DB) |
| GET | `/api/v1/history/sessions/{id}/equity-curve` | Equity snapshots (from DB) |
| POST | `/api/v1/history/sessions/compare` | Compare multiple sessions side-by-side |

### Agents (replay-engine:8001)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agents/register` | Register new agent |
| DELETE | `/api/v1/agents/{id}` | Remove agent |
| GET | `/api/v1/agents/` | List all agents |
| GET | `/api/v1/agents/{id}` | Agent detail + stats |
| POST | `/api/v1/agents/{id}/order` | Place order for agent |
| POST | `/api/v1/agents/{id}/close` | Close agent position |
| POST | `/api/v1/agents/predict` | Submit prediction (HTTP alternative to Redis) |
| GET | `/api/v1/agents/predict/stats` | Prediction processing statistics |
| GET | `/api/v1/agents/leaderboard/rankings` | Agent rankings (sortable) |
| POST | `/api/v1/agents/tournament/create` | Create tournament |
| POST | `/api/v1/agents/tournament/start` | Start tournament |
| POST | `/api/v1/agents/tournament/pause` | Pause tournament |
| POST | `/api/v1/agents/tournament/resume` | Resume tournament |
| POST | `/api/v1/agents/tournament/stop` | Stop tournament |
| GET | `/api/v1/agents/tournament/standings` | Current standings |
| GET | `/api/v1/agents/tournament/state` | Full tournament state |

### Dashboard (dashboard-backend:8000)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Dashboard health (Redis + engine connectivity) |
| WS | `/ws/live` | WebSocket live stream (market data + engine updates) |
| * | `/api/v1/*` | Proxied to replay-engine |

## Redis Pub/Sub Channels

| Channel | Publisher | Subscriber | Data |
|---------|-----------|------------|------|
| `market_data_vn30f1m` | data-feed | replay-engine, dashboard | `{timestamp, close, regime}` |
| `engine_updates` | replay-engine | dashboard | `{type, data}` |
| `prediction_votes` | AI agents | replay-engine | `{agent_id, action, confidence, volume}` |
| `final_decision` | adjudicator | replay-engine | `{agent_id, action, confidence}` |

## Docker Services

| Service | Port | Image | Depends On |
|---------|------|-------|------------|
| redis | 6379 | redis:7-alpine | — |
| mysql | 3306 | mysql:8.0 | — |
| replay-engine | 8001 | ./services/replay-engine | redis, mysql |
| dashboard-backend | 8000 | ./services/dashboard | redis, replay-engine |
| dashboard-frontend | 3000 | ./services/dashboard/frontend | dashboard-backend |
| data-feed | — | ./services/data-feed | redis |

## Test Summary

| Phase | Tests | Coverage |
|-------|-------|----------|
| Phase 1: Core Exchange | 68 | Fees, margin, rollover, metrics, sessions, slippage, engine, API |
| Phase 2: Dashboard | 36 | WebSocket, Redis bridge, health, proxies, orders, sessions, frontend |
| Phase 3: Persistence | 38 | DB init, models CRUD, repository, auto-saver, history API, comparison |
| Phase 4: Agent Integration | 46 | Config, registration, orders, predictions, leaderboard, tournament, API |
| **Total** | **188** | **All passing** |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Database | MySQL 8.0 (prod), SQLite (test) |
| ORM | SQLAlchemy 2.0 Async + aiomysql |
| Cache/Messaging | Redis 7 + Pub/Sub |
| Frontend | React 18, Vite, TypeScript |
| UI | Tailwind CSS (dark trading theme) |
| Charts | TradingView Lightweight Charts v4.2 |
| Containerization | Docker + docker-compose |

## Codebase Stats

- **Source code**: ~4,100 lines (replay-engine + dashboard)
- **Test code**: ~2,100 lines (188 tests)
- **Total files**: 35+ source files across 2 services
