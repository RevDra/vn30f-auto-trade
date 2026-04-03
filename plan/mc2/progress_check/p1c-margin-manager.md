# p1c-margin-manager — MarginManager + price limits

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: (none directly)

## Description
Initial margin 17% (VSD), maintenance ~13.6% (80% initial), max 500 contracts/account, ±7% price limit circuit breaker.

## Key Numbers
| Param | Value | Source |
|-------|-------|--------|
| Initial margin | 17% | VSD 20/03/2026 |
| Maintenance margin | ~13.6% | 80% × initial |
| Price limit | ±7% | HNX quy định |
| Max contracts | 500/account | Retail limit |
| Multiplier | 100,000 VND | Contract spec |

## Acceptance Criteria
- [ ] `MarginManager` class in `app/risk.py`
- [ ] `required_margin(price, volume)` → VND
- [ ] `check_margin_call(equity, price, volume)` → margin_call/force_close
- [ ] `validate_price_limit(new_price, ref_price)` → bool
- [ ] `can_open_position(account, volume)` → bool
- [ ] Rejects order when insufficient margin (raises exception)

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
