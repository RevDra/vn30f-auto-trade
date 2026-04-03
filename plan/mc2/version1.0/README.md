# VN30F Mock Exchange v1.0

Sàn giao dịch mô phỏng VN30F Futures với dashboard real-time và hệ thống AI agent tournament.

## Features

- **Mock Exchange Engine** — Mô phỏng đầy đủ VN30F: phí giao dịch 3 lớp (broker + HNX + VSD + thuế TNCN), margin 17%, price limit ±7%, rollover 3rd Thursday, slippage model
- **Real-time Dashboard** — Candlestick chart, equity curve, metrics cards, trade history, manual order panel
- **MySQL Persistence** — Auto-save trades + equity snapshots, session history, cross-session comparison
- **Agent Tournament** — Register AI agents, isolated sessions, leaderboard rankings, tournament mode

## Architecture

```
[Data Feed] → Redis Pub/Sub → [Replay Engine] ←→ [MySQL]
                    ↕                   ↕
              [AI Agents]        [Dashboard Backend] → [React Frontend]
```

Xem chi tiết: [ARCHITECTURE.md](./ARCHITECTURE.md)

## Quick Start

### 1. Chạy với Docker (recommended)

```bash
# Clone và start toàn bộ stack
docker-compose up -d redis mysql
sleep 5  # wait for MySQL init
docker-compose up -d replay-engine dashboard-backend dashboard-frontend

# Check health
curl http://localhost:8000/health
```

### 2. Chạy local (development)

```bash
# Terminal 1: Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Terminal 2: Replay Engine
cd services/replay-engine
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8001

# Terminal 3: Dashboard Backend
cd services/dashboard
pip install -r requirements.txt
REPLAY_ENGINE_URL=http://localhost:8001 uvicorn backend.app:app --host 0.0.0.0 --port 8000

# Terminal 4: Dashboard Frontend
cd services/dashboard/frontend
npm install
npm run dev  # http://localhost:3000
```

### 3. Chạy tests

```bash
# Tạo venv
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn redis httpx pydantic pytest pytest-asyncio "sqlalchemy[asyncio]" aiosqlite aiomysql

# Test toàn bộ (188 tests)
cd services/replay-engine && python -m pytest tests/ -v
cd ../dashboard && python -m pytest tests/ -v
```

## Quickstart: Manual Trading

```bash
# 1. Check PnL
curl http://localhost:8001/api/v1/pnl

# 2. Đặt lệnh LONG 2 hợp đồng
curl -X POST http://localhost:8001/api/v1/order \
  -H "Content-Type: application/json" \
  -d '{"action": "LONG", "volume": 2}'

# 3. Đóng vị thế
curl -X POST http://localhost:8001/api/v1/close-position

# 4. Xem lịch sử giao dịch
curl http://localhost:8001/api/v1/trades
```

## Quickstart: Agent Tournament

```bash
# 1. Tạo tournament
curl -X POST http://localhost:8001/api/v1/agents/tournament/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Q1 Championship", "initial_balance": 500000000}'

# 2. Đăng ký agents
curl -X POST http://localhost:8001/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "rl-agent", "name": "RL Bot", "confidence_threshold": 0.7}'

curl -X POST http://localhost:8001/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "sentiment-bot", "name": "Sentiment Bot", "confidence_threshold": 0.6}'

# 3. Start tournament
curl -X POST http://localhost:8001/api/v1/agents/tournament/start

# 4. Submit predictions (hoặc qua Redis prediction_votes channel)
curl -X POST http://localhost:8001/api/v1/agents/predict \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "rl-agent", "action": "LONG", "confidence": 0.85, "volume": 3}'

# 5. Xem leaderboard
curl http://localhost:8001/api/v1/agents/leaderboard/rankings?sort_by=pnl

# 6. Xem standings
curl http://localhost:8001/api/v1/agents/tournament/standings

# 7. Kết thúc tournament
curl -X POST http://localhost:8001/api/v1/agents/tournament/stop
```

## Quickstart: Session History (requires MySQL)

```bash
# Cần DATABASE_URL environment variable
export DATABASE_URL="mysql+aiomysql://root:rootpass@localhost:3306/vn30f1m_db"

# Xem lịch sử sessions
curl http://localhost:8001/api/v1/history/sessions

# So sánh sessions
curl -X POST http://localhost:8001/api/v1/history/sessions/compare \
  -H "Content-Type: application/json" \
  -d '["session-1", "session-2"]'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Redis server host |
| `REDIS_PORT` | 6379 | Redis server port |
| `DATABASE_URL` | — | MySQL connection URL (persistence enabled if set) |
| `REPLAY_ENGINE_URL` | http://replay-engine:8001 | Engine URL for dashboard proxy |

## Project Stats

| Metric | Value |
|--------|-------|
| Source code | ~4,100 lines |
| Test code | ~2,100 lines |
| Total tests | 188 (all passing) |
| API endpoints | 30+ |
| Modules | 17 Python + 8 TypeScript |
| Docker services | 6 |
