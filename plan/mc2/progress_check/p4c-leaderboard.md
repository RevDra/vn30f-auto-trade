# p4c-leaderboard — Leaderboard API

- **Status**: ✅ done
- **Depends on**: p4b-agent-isolation
- **Blocks**: p4d-tournament

## Description
Compare agent performance: PnL, win rate, Sharpe, drawdown. Sortable leaderboard API + dashboard page.

## Acceptance Criteria
- [ ] GET /api/v1/leaderboard — sorted by net PnL
- [ ] Supports sort_by: pnl, win_rate, sharpe, drawdown
- [ ] Includes trade count, active since
- [ ] Dashboard leaderboard table component
- [ ] Real-time update as agents trade

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (46/46)
