# p4a-prediction-subscribe — Subscribe prediction_votes

- **Status**: ✅ done
- **Depends on**: p1i-api-expansion
- **Blocks**: p4b-agent-isolation

## Description
Subscribe Redis `prediction_votes` / `final_decision` channels, convert to internal orders.

## Acceptance Criteria
- [ ] Listen to `prediction_votes` channel
- [ ] Parse agent signals (direction, confidence, volume)
- [ ] Convert to internal order format
- [ ] Validate margin before executing
- [ ] Log rejected orders (insufficient margin, outside hours)

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (46/46)
