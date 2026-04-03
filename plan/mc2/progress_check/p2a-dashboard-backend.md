# p2a-dashboard-backend — Dashboard FastAPI + WebSocket

- **Status**: ✅ done
- **Depends on**: p1i-api-expansion
- **Blocks**: p2b-redis-ws-bridge, p2c-frontend-scaffold

## Description
FastAPI backend cho dashboard: REST API proxy tới replay-engine + native WebSocket server cho real-time updates.

## Acceptance Criteria
- [ ] `services/dashboard/backend/main.py` — FastAPI app
- [ ] `ws_manager.py` — WebSocket connection manager (broadcast)
- [ ] REST proxy: /api/dashboard/pnl, /api/dashboard/trades
- [ ] WebSocket: /ws/live (push tick data + engine updates)
- [ ] Health check: /health (redis + replay-engine connectivity)
- [ ] CORS configured for frontend dev server

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (36/36)
