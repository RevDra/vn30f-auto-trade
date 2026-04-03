# p2e-equity-metrics — EquityCurve + MetricsCards

- **Status**: ✅ done
- **Depends on**: p2c-frontend-scaffold
- **Blocks**: (none directly)

## Description
Equity curve line chart + metrics dashboard cards (Win Rate, PnL, Drawdown, Sharpe).

## Acceptance Criteria
- [ ] `EquityCurve.tsx` — line chart (lightweight-charts or recharts)
- [ ] `MetricsCards.tsx` — 4 cards with live values
  - Win Rate %
  - Total PnL (VND)
  - Max Drawdown %
  - Sharpe Ratio
- [ ] Data from `/api/v1/pnl` endpoint + WebSocket updates
- [ ] Color: green for positive, red for negative
- [ ] Auto-refresh every tick

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (36/36)
