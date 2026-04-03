# p1d-rollover-fix — Fix rollover logic

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: (none directly)

## Description
Replace hardcoded day 16-22 check with proper 3rd Thursday calculation per Pinetree/HNX spec.

## Key Facts
- Expiry = 3rd Thursday of maturity month (Pinetree, HNX)
- Rollover Friday = day after expiry
- Current code checks `weekday==4 && 16<=day<=22` — edge cases fail

## Acceptance Criteria
- [ ] `get_expiry_date(year, month)` → datetime (3rd Thursday)
- [ ] `is_rollover_friday(date)` uses calculated expiry
- [ ] Tests: months starting on different weekdays
- [ ] Tests: edge case month starting Thursday/Friday

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
