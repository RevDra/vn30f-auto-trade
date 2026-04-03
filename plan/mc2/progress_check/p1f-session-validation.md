# p1f-session-validation — Trading session hours

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: (none directly)

## Description
Validate orders within VN30F sessions: ATO 8:45-9:00, CONT 9:00-11:30 & 13:00-14:30, ATC 14:30-14:45.

## Sessions
| Session | Start | End |
|---------|-------|-----|
| ATO | 08:45 | 09:00 |
| CONT1 | 09:00 | 11:30 |
| CONT2 | 13:00 | 14:30 |
| ATC | 14:30 | 14:45 |

## Acceptance Criteria
- [ ] `TradingSessionValidator` class
- [ ] `is_trading_hour(dt)` → bool
- [ ] `get_session_name(dt)` → Optional[str]
- [ ] Orders rejected outside trading hours (configurable: strict/relaxed mode)
- [ ] Tests cover session boundaries and lunch break

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
