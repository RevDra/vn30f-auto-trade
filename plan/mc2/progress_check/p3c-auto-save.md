# p3c-auto-save — Auto-save trades + snapshots

- **Status**: ✅ done
- **Depends on**: p3b-repository-layer
- **Blocks**: p3d-session-history

## Description
Auto-persist: every trade → trades table, equity snapshot every 60s → equity_snapshots table, session summary on close.

## Acceptance Criteria
- [ ] Trade auto-saved on open AND close
- [ ] Equity snapshot saved every 60 seconds (configurable interval)
- [ ] Session auto-saved on create and on end
- [ ] Batch insert for snapshots (avoid N+1)
- [ ] Graceful handling if MySQL is down (log warning, don't crash)

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (38/38)
