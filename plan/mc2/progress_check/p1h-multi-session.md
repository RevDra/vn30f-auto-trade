# p1h-multi-session — SessionManager multi-session

- **Status**: ✅ done
- **Depends on**: p1e-real-metrics
- **Blocks**: p1i-api-expansion

## Description
Replace global singleton with SessionManager supporting concurrent sessions for strategy comparison.

## Acceptance Criteria
- [ ] `SessionManager` class in `app/session.py`
- [ ] `create_session(strategy, balance)` → session_id
- [ ] `get_active_engine()` → ReplayEngine
- [ ] `switch_session(session_id)` → ok/error
- [ ] `list_sessions()` → list of session summaries
- [ ] Multiple sessions can coexist in memory
- [ ] Each session has isolated PnL, trades, metrics

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
