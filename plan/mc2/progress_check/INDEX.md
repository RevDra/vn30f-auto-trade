# Progress Check — Mock Exchange + Dashboard

> Auto-generated from improved plan. Each file tracks 1 todo.
> **Convention**: Cập nhật status + error log mỗi khi work trên todo.

## Phases

### Phase 1: Core Exchange Engine
| File | Todo ID | Status | Title |
|------|---------|--------|-------|
| [p1a-module-structure.md](p1a-module-structure.md) | `p1a` | ✅ done | Tách module structure replay-engine |
| [p1b-fee-calculator.md](p1b-fee-calculator.md) | `p1b` | ✅ done | FeeCalculator chính xác |
| [p1c-margin-manager.md](p1c-margin-manager.md) | `p1c` | ✅ done | MarginManager + price limits |
| [p1d-rollover-fix.md](p1d-rollover-fix.md) | `p1d` | ✅ done | Fix rollover logic |
| [p1e-real-metrics.md](p1e-real-metrics.md) | `p1e` | ✅ done | Real metrics calculation |
| [p1f-session-validation.md](p1f-session-validation.md) | `p1f` | ✅ done | Trading session hours |
| [p1g-slippage-model.md](p1g-slippage-model.md) | `p1g` | ✅ done | Volume-dependent slippage |
| [p1h-multi-session.md](p1h-multi-session.md) | `p1h` | ✅ done | SessionManager multi-session |
| [p1i-api-expansion.md](p1i-api-expansion.md) | `p1i` | ✅ done | Expand API + error handling |
| [p1j-unit-tests.md](p1j-unit-tests.md) | `p1j` | ✅ done | Unit tests all modules |

### Phase 2: Dashboard MVP
| File | Todo ID | Status | Title |
|------|---------|--------|-------|
| [p2a-dashboard-backend.md](p2a-dashboard-backend.md) | `p2a` | ✅ done | Dashboard FastAPI + WebSocket |
| [p2b-redis-ws-bridge.md](p2b-redis-ws-bridge.md) | `p2b` | ✅ done | Redis → WebSocket bridge |
| [p2c-frontend-scaffold.md](p2c-frontend-scaffold.md) | `p2c` | ✅ done | Frontend React + Vite + Tailwind |
| [p2d-candlestick-chart.md](p2d-candlestick-chart.md) | `p2d` | ✅ done | CandlestickChart component |
| [p2e-equity-metrics.md](p2e-equity-metrics.md) | `p2e` | ✅ done | EquityCurve + MetricsCards |
| [p2f-trade-position.md](p2f-trade-position.md) | `p2f` | ✅ done | TradeHistory + PositionPanel |
| [p2g-order-panel.md](p2g-order-panel.md) | `p2g` | ✅ done | OrderPanel manual trading |
| [p2h-docker.md](p2h-docker.md) | `p2h` | ✅ done | Docker integration |

### Phase 3: Persistence
| File | Todo ID | Status | Title |
|------|---------|--------|-------|
| [p3a-mysql-schema.md](p3a-mysql-schema.md) | `p3a` | ✅ done | MySQL schema migration |
| [p3b-repository-layer.md](p3b-repository-layer.md) | `p3b` | ✅ done | SQLAlchemy repository |
| [p3c-auto-save.md](p3c-auto-save.md) | `p3c` | ✅ done | Auto-save trades + snapshots |
| [p3d-session-history.md](p3d-session-history.md) | `p3d` | ✅ done | Session history + replay |

### Phase 4: Agent Integration
| File | Todo ID | Status | Title |
|------|---------|--------|-------|
| [p4a-prediction-subscribe.md](p4a-prediction-subscribe.md) | `p4a` | ✅ done | Subscribe prediction_votes |
| [p4b-agent-isolation.md](p4b-agent-isolation.md) | `p4b` | ✅ done | Agent session isolation |
| [p4c-leaderboard.md](p4c-leaderboard.md) | `p4c` | ✅ done | Leaderboard API |
| [p4d-tournament.md](p4d-tournament.md) | `p4d` | ✅ done | Tournament mode |

## Status Legend
- ⬜ pending
- 🔄 in_progress
- ✅ done
- 🚫 blocked
