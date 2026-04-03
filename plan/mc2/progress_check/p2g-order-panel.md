# p2g-order-panel — OrderPanel manual trading

- **Status**: ✅ done
- **Depends on**: p2c-frontend-scaffold
- **Blocks**: (none directly)

## Description
Manual trading panel: LONG/SHORT/CLOSE buttons, volume input, confirmation dialog.

## Acceptance Criteria
- [ ] `OrderPanel.tsx` component
- [ ] LONG button (green), SHORT button (red), CLOSE button (gray)
- [ ] Volume input with +/- steppers (1-500)
- [ ] Confirmation modal before executing
- [ ] Sends POST to `/api/v1/trade` or `/api/v1/close-position`
- [ ] Shows estimated cost (margin + fees) before confirmation
- [ ] Disabled when no active session or outside trading hours

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (36/36)
