# p1g-slippage-model — Volume-dependent slippage

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: (none directly)

## Description
Base 2 ticks + 1 tick per 5 contracts + rollover impact + ATO/ATC liquidity factor.

## Model
```
slippage_ticks = base(2) + volume_impact(vol//5) + rollover(2 if rollover_friday) + session_factor
session_factor: ATO/ATC = +1 tick, CONT = 0
```

## Acceptance Criteria
- [ ] `calculate_slippage(action, volume, session, is_rollover)` → float
- [ ] Returns different slippage for different volumes
- [ ] Rollover day adds extra slippage
- [ ] Tests: 1 contract vs 10 contracts vs 50 contracts

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
