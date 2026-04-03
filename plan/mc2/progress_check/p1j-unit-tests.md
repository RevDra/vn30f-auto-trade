# p1j-unit-tests — Unit tests all modules

- **Status**: ✅ done
- **Depends on**: p1i-api-expansion
- **Blocks**: (none — can proceed to Phase 2)

## Description
14+ test cases: fee calculation, margin check, rollover edge cases, metrics accuracy, API validation.

## Test Matrix
| Test | Module | Priority |
|------|--------|----------|
| test_fee_per_side | fees.py | HIGH |
| test_fee_round_trip | fees.py | HIGH |
| test_fee_tax_calculation | fees.py | HIGH |
| test_margin_required | risk.py | HIGH |
| test_margin_call_detection | risk.py | HIGH |
| test_price_limit_validation | risk.py | HIGH |
| test_rollover_3rd_thursday | engine.py | HIGH |
| test_rollover_edge_months | engine.py | MEDIUM |
| test_win_rate | metrics.py | HIGH |
| test_max_drawdown | metrics.py | HIGH |
| test_sharpe_ratio | metrics.py | MEDIUM |
| test_session_hours | engine.py | MEDIUM |
| test_slippage_volume | engine.py | MEDIUM |
| test_api_order_validation | test_api.py | HIGH |
| test_api_error_codes | test_api.py | HIGH |
| test_api_pnl_response | test_api.py | HIGH |

## Acceptance Criteria
- [ ] All 16+ tests written and passing
- [ ] `pytest` runs clean with 0 failures
- [ ] Coverage > 80% on new modules

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
