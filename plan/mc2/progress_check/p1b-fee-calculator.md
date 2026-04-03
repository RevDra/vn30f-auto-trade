# p1b-fee-calculator — FeeCalculator chính xác

- **Status**: ✅ done
- **Depends on**: p1a-module-structure
- **Blocks**: (none directly)

## Description
Implement multi-layer fee: broker (2,000 VND) + exchange (2,700 VND HNX) + clearing (2,550 VND VSD) + TNCN tax (0.1%). Configurable per broker tier.

## Key Numbers (from VPS/SSI/VSD research 2025-2026)
| Fee | Amount | Source |
|-----|--------|--------|
| Broker (VPS default) | 2,000 VND/HĐ | VPS biểu phí 05/2025 |
| Exchange (HNX) | 2,700 VND/HĐ | SSI, TCBS, VPS |
| Clearing (VSD) | 2,550 VND/HĐ | VSD, SSI |
| TNCN tax | 0.1% × transfer value | Thông tư 101/2021 |

## Acceptance Criteria
- [ ] `FeeCalculator` class in `app/fees.py`
- [ ] `calculate_per_side(volume)` → VND amount
- [ ] `calculate_tax(price, volume)` → VND amount
- [ ] `total_round_trip(entry, exit, volume)` → breakdown dict
- [ ] Configurable via `ExchangeConfig`
- [ ] Unit tests verify exact numbers

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (68/68)
