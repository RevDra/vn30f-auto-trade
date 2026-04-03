# p2f-trade-position — TradeHistory + PositionPanel

- **Status**: ✅ done
- **Depends on**: p2c-frontend-scaffold
- **Blocks**: (none directly)

## Description
Trade history table (sortable/filterable) + active position panel showing unrealized PnL.

## Acceptance Criteria
- [ ] `TradeHistory.tsx` — table with columns: time, direction, volume, entry, exit, PnL, fees
- [ ] Sortable by time, PnL
- [ ] Filter by direction (LONG/SHORT)
- [ ] `PositionPanel.tsx` — shows current position:
  - Direction, volume, entry price
  - Current price, unrealized PnL
  - Margin used, margin available
- [ ] Live updates via WebSocket

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (36/36)
