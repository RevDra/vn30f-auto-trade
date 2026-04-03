# p1i-api-expansion — Expand API + error handling

- **Status**: ✅ done
- **Depends on**: p1h-multi-session
- **Blocks**: p1j-unit-tests, p2a-dashboard-backend, p4a-prediction-subscribe

## Description
Add /health, /trades, /equity-curve, /close-position, /reset, /sessions endpoints. Proper HTTP status codes + Pydantic validation.

## New Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Service health + redis status |
| GET | /api/v1/trades | Trade history (paginated) |
| GET | /api/v1/equity-curve | Equity curve data |
| POST | /api/v1/close-position | Force close active position |
| POST | /api/v1/reset | Reset engine state |
| GET | /api/v1/sessions | List all sessions |
| POST | /api/v1/sessions | Create new session |
| PUT | /api/v1/sessions/{id}/activate | Switch active session |

## Acceptance Criteria
- [ ] All endpoints above implemented
- [ ] `OrderRequest` Pydantic model with validation
- [ ] Errors return proper HTTP status codes (400, 422, 404)
- [ ] `InsufficientMarginError` → 422
- [ ] `ValueError` → 400
- [ ] Publish `engine_updates` to Redis on each trade/tick

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
