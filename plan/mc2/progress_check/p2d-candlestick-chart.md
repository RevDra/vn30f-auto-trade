# p2d-candlestick-chart — CandlestickChart component

- **Status**: ✅ done
- **Depends on**: p2b-redis-ws-bridge, p2c-frontend-scaffold
- **Blocks**: (none directly)

## Description
TradingView Lightweight Charts v4.2+ — live candlestick from market_data channel via WebSocket.

## Tech
- Library: `lightweight-charts` (npm, Apache 2.0, 35KB)
- Features: OHLCV candles, volume bars, crosshair, time axis
- Update: real-time via WebSocket `market_data` messages

## Acceptance Criteria
- [ ] `CandlestickChart.tsx` component
- [ ] Shows real-time candles from WebSocket feed
- [ ] Volume bars overlay
- [ ] Crosshair with price/time tooltip
- [ ] Time range selector (1m, 5m, 15m, 1h)
- [ ] Responsive resize

## Progress Log

## Error Log

### 2025-04-03 — Completed
- All code implemented and tests passing (36/36)
