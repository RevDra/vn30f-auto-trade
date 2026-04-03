# p2b-redis-ws-bridge — Redis → WebSocket bridge

- **Status**: ✅ done
- **Depends on**: p2a-dashboard-backend
- **Blocks**: p2d-candlestick-chart

## Description
Subscribe `engine_updates` + `market_data_vn30f1m` Redis channels → broadcast to all connected WebSocket clients.

## Acceptance Criteria
- [ ] `redis_subscriber.py` subscribes to both channels
- [ ] Messages parsed and forwarded to WebSocket manager
- [ ] Handles reconnection on Redis disconnect
- [ ] Message rate limiting (throttle to max 10/sec per client if needed)
- [ ] Clean shutdown on SIGTERM

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (36/36)
