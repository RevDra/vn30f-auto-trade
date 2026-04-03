# p3a-mysql-schema — MySQL schema migration

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: p3b-repository-layer

## Description
Create 3 tables: trading_sessions, trades, equity_snapshots. Include new fields: commission, tax, sharpe_ratio, session_name.

## Schema Summary
- `trading_sessions`: id, started_at, ended_at, strategy, initial_balance, final_pnl, total_trades, win_rate, max_drawdown, sharpe_ratio, total_commission, total_tax, status
- `trades`: session_id, entry/exit time+price, direction, volume, slippage, commission, tax, gross_pnl, net_pnl, status
- `equity_snapshots`: session_id, timestamp, equity, pnl_realized, pnl_unrealized, margin_used, margin_available, regime, session_name

## Acceptance Criteria
- [ ] SQL migration file in `services/replay-engine/migrations/`
- [ ] Tables created successfully in MySQL container
- [ ] Correct foreign keys and indexes
- [ ] Alembic/manual migration script documented

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (38/38)
