# p1e-real-metrics — Real metrics calculation

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: p1h-multi-session

## Description
Win rate, max drawdown, Sharpe ratio, equity curve tracking — replace all hardcoded 0.0 values.

## Acceptance Criteria
- [ ] `MetricTracker` class in `app/metrics.py`
- [ ] `calculate_win_rate()` from trade_history
- [ ] `calculate_max_drawdown()` from equity_curve
- [ ] `calculate_sharpe_ratio()` (annualized, risk-free = 0)
- [ ] `equity_curve: List[float]` updated each tick
- [ ] `timeseries_pnl: List[dict]` with time+pnl+regime
- [ ] `GET /api/v1/pnl` returns real data, not hardcoded

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
