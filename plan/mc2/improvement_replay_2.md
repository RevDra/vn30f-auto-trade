# Đánh Giá & Cải Tiến Plan: Replay Engine + Dashboard

## Mục tiêu
Phát triển mock exchange (replay-engine + dashboard) hoàn chỉnh trước, sau đó core agents sẽ đấu trade mô phỏng.

---

## PHẦN 1: ĐÁNH GIÁ PLAN GỐC (improvement_replay_1.md)

### ✅ Điểm mạnh của plan gốc
1. **Phân tích hiện trạng rất kỹ** — cover hết 13 thiếu sót từ CRITICAL → LOW
2. **Priority phân loại hợp lý** — P0/P1/P2/P3 đúng logic
3. **MySQL schema tốt** — 3 bảng (sessions, trades, equity_snapshots) đủ dùng
4. **Cross-service impact analysis chính xác** — tất cả thay đổi backward compatible
5. **Test coverage plan** đầy đủ 14 test cases

### ❌ Sai sót & Thiếu sót nghiêm trọng (từ deep research)

#### 1. 🔴 PHÍ GIAO DỊCH SAI — Underestimate 2-3x
Plan ghi: `4,500 VND/contract/chiều = 0.045 điểm`

**Thực tế từ VPS, SSI, TCBS (2025-2026):**
| Loại phí | Giá |
|----------|-----|
| Phí broker (VPS/SSI) | 500 ~ 3,000 VND/HĐ (tùy volume tier) |
| Phí Sở GDCK (HNX) | 2,700 VND/HĐ |
| Phí bù trừ VSD | 2,550 VND/HĐ khớp lệnh |
| **Tổng 1 chiều** | **~5,750 — 8,250 VND/HĐ** |
| **Tổng round-trip** | **~11,500 — 16,500 VND/HĐ** |
| **Quy đổi điểm (1 chiều)** | **~0.058 — 0.083 điểm** |

→ Plan ghi 0.045 điểm/chiều = **thiếu ~30-80%** so với thực tế.

#### 2. 🔴 THIẾU THUẾ TNCN trên phái sinh
**Thuế TNCN = 0.1% × Giá chuyển nhượng** (theo Thông tư 101/2021/TT-BTC)
- Giá chuyển nhượng = (Settlement price × 100,000 × contracts × 17%) / 2
- Ví dụ: VN30F = 1,300, 1 contract → Thuế = 0.1% × (1300 × 100000 × 1 × 0.17) / 2 = 11,050 VND
- **Plan hoàn toàn bỏ qua** khoản này (ghi "phái sinh không chịu thuế" — SAI)

#### 3. 🟠 MAINTENANCE MARGIN KHÔNG CÒN LÀ 13%
- VSD tăng initial margin từ 13% → 17% từ 15/12/2022
- Plan ghi maintenance = 13% nhưng không có nguồn. Thực tế maintenance ≈ 80% × initial = ~13.6% (tùy broker)
- Cần model configurable, không hardcode

#### 4. 🟠 HỆ SỐ NHÂN KHÁC NHAU giữa plan và thực tế
Plan ghi `1 điểm = 100,000 VND` — ĐÚNG cho contract multiplier.
Nhưng MBS formula dùng `Hệ số nhân = 100,000`, VSD formula dùng cùng giá trị.
→ OK nhưng cần ghi rõ đây là contract multiplier, không phải point value.

#### 5. 🟡 THIẾU HOÀN TOÀN: Trading Session Hours & Circuit Breaker
VN30F giao dịch theo phiên cố định:
| Phiên | Thời gian |
|-------|-----------|
| ATO (Mở cửa) | 8:45 - 9:00 |
| Liên tục sáng | 9:00 - 11:30 |
| Nghỉ trưa | 11:30 - 13:00 |
| Liên tục chiều | 13:00 - 14:30 |
| ATC (Đóng cửa) | 14:30 - 14:45 |

- Biên độ dao động: ±7% so với giá tham chiếu
- Mock exchange PHẢI mô phỏng giới hạn này nếu muốn realistic
- Plan không nhắc đến

#### 6. 🟡 PLAN ĐẶT SAI PRIORITY theo mục tiêu user
User muốn: **Mock exchange + Dashboard TRƯỚC → Agents trade SAU**
Plan đặt P0: "Subscribe prediction_votes" (= kết nối agents)
→ Nên đổi P0 thành: **Core exchange engine + Dashboard**, agents subscribe sau.

#### 7. 🟡 DASHBOARD KHÔNG ĐƯỢC ĐỀ CẬP
Plan 700 dòng nhưng ZERO nội dung về Dashboard service:
- Không có UI architecture
- Không có WebSocket real-time design
- Không có chart library recommendation
- Hiện tại `services/dashboard/main.py` = EMPTY file

---

## PHẦN 2: IMPROVED PLAN — Mock Exchange + Dashboard

### Kiến trúc tổng thể

```
┌─────────────────────────────────────────────┐
│                 Dashboard (Web UI)           │
│  Next.js / React + TradingView Lightweight   │
│  Charts + WebSocket client                   │
└─────────────┬────────────────────────────────┘
              │ WebSocket + REST
┌─────────────▼────────────────────────────────┐
│           Dashboard API (FastAPI)             │
│  WS /ws/live    REST /api/v1/*               │
│  Subscribes Redis → broadcasts WS            │
└─────────────┬────────────────────────────────┘
              │ Redis Pub/Sub
┌─────────────▼────────────────────────────────┐
│         Replay Engine (Mock Exchange)         │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Matching │ │  Risk    │ │  Fee         │  │
│  │ Engine   │ │  Engine  │ │  Calculator  │  │
│  └──────────┘ └──────────┘ └──────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Session  │ │  Metric  │ │  Persistence │  │
│  │ Manager  │ │  Tracker │ │  (MySQL)     │  │
│  └──────────┘ └──────────┘ └──────────────┘  │
│  Publishes: engine_updates (Redis)           │
│  Subscribes: market_data_vn30f1m             │
│             + agent_orders (future)          │
└─────────────┬────────────────────────────────┘
              │ Redis Pub/Sub
┌─────────────▼────────────────────────────────┐
│         Data Feed (existing)                  │
│  Publishes: market_data_vn30f1m              │
└──────────────────────────────────────────────┘
```

### Phase 1: Core Exchange Engine (replay-engine refactor)

#### 1.1 Tách module structure
```
services/replay-engine/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, WS
│   ├── engine.py            # class ReplayEngine (matching)
│   ├── risk.py              # MarginManager, position limits
│   ├── fees.py              # FeeCalculator (broker + exchange + VSD + tax)
│   ├── metrics.py           # MetricTracker (win_rate, drawdown, sharpe)
│   ├── session.py           # SessionManager (multi-session)
│   ├── persistence.py       # MySQL repository
│   ├── listeners.py         # Redis subscribers
│   ├── schemas.py           # Request/Response models (local)
│   ├── config.py            # Exchange config (fees, margins, sessions)
│   └── constants.py         # VN30F constants
├── tests/
│   ├── test_engine.py
│   ├── test_risk.py
│   ├── test_fees.py
│   ├── test_metrics.py
│   ├── test_api.py
│   └── conftest.py
├── requirements.txt
└── Dockerfile
```

#### 1.2 Fee Model (CHÍNH XÁC theo research)
```python
class FeeCalculator:
    """VN30F fee structure (2025-2026, configurable per broker)"""
    def __init__(self, config: ExchangeConfig):
        self.broker_fee = config.broker_fee_per_contract     # 2,000 VND default
        self.exchange_fee = config.exchange_fee_per_contract  # 2,700 VND (HNX)
        self.clearing_fee = config.clearing_fee_per_contract  # 2,550 VND (VSD)
        self.tax_rate = config.personal_income_tax_rate       # 0.001 (0.1%)
        self.margin_rate = config.initial_margin_rate         # 0.17
        self.multiplier = config.contract_multiplier          # 100,000 VND

    def calculate_per_side(self, volume: int) -> float:
        """Phí 1 chiều (mở hoặc đóng)"""
        return (self.broker_fee + self.exchange_fee + self.clearing_fee) * volume

    def calculate_tax(self, price: float, volume: int) -> float:
        """Thuế TNCN phái sinh"""
        transfer_value = (price * self.multiplier * volume * self.margin_rate) / 2
        return transfer_value * self.tax_rate

    def total_round_trip(self, entry_price, exit_price, volume) -> dict:
        """Tổng phí round-trip (mở + đóng + thuế)"""
        side_fee = self.calculate_per_side(volume) * 2  # 2 chiều
        entry_tax = self.calculate_tax(entry_price, volume)
        exit_tax = self.calculate_tax(exit_price, volume)
        return {
            "broker_fee": self.broker_fee * volume * 2,
            "exchange_fee": self.exchange_fee * volume * 2,
            "clearing_fee": self.clearing_fee * volume * 2,
            "tax": entry_tax + exit_tax,
            "total_vnd": side_fee + entry_tax + exit_tax,
            "total_points": (side_fee + entry_tax + exit_tax) / self.multiplier
        }
```

#### 1.3 Risk Engine
```python
class MarginManager:
    def __init__(self, config: ExchangeConfig):
        self.initial_margin_rate = 0.17      # VSD quy định, cập nhật 20/03/2026
        self.maintenance_margin_rate = 0.136  # ~80% initial (broker-dependent)
        self.price_limit_pct = 0.07          # ±7% biên độ
        self.multiplier = 100_000
        self.max_contracts_per_account = 500  # giới hạn thực tế cho retail

    def required_margin(self, price, volume) -> float:
        return price * self.multiplier * volume * self.initial_margin_rate

    def maintenance_margin(self, price, volume) -> float:
        return price * self.multiplier * volume * self.maintenance_margin_rate

    def check_margin_call(self, account_equity, price, volume) -> dict:
        """Check margin call / force liquidation"""
        maintenance = self.maintenance_margin(price, volume)
        return {
            "equity": account_equity,
            "maintenance_required": maintenance,
            "margin_call": account_equity < maintenance,
            "force_close": account_equity < maintenance * 0.8
        }

    def validate_price_limit(self, new_price, reference_price) -> bool:
        """Check ±7% price limit"""
        upper = reference_price * (1 + self.price_limit_pct)
        lower = reference_price * (1 - self.price_limit_pct)
        return lower <= new_price <= upper
```

#### 1.4 Rollover fix (ĐÚNG theo Pinetree / HNX)
```python
def get_expiry_date(year: int, month: int) -> datetime:
    """Ngày đáo hạn = Thứ 5 tuần thứ 3 (3rd Thursday) của tháng"""
    first_day = datetime(year, month, 1)
    # Thursday = weekday 3
    days_until_thursday = (3 - first_day.weekday()) % 7
    first_thursday = first_day + timedelta(days=days_until_thursday)
    third_thursday = first_thursday + timedelta(days=14)
    return third_thursday
```

#### 1.5 Trading Session Validation
```python
class TradingSessionValidator:
    """Validate trading within VN30F session hours"""
    SESSIONS = [
        ("ATO",  time(8, 45), time(9, 0)),
        ("CONT1", time(9, 0), time(11, 30)),
        ("CONT2", time(13, 0), time(14, 30)),
        ("ATC",  time(14, 30), time(14, 45)),
    ]

    def is_trading_hour(self, dt: datetime) -> bool:
        t = dt.time()
        return any(start <= t <= end for _, start, end in self.SESSIONS)

    def get_session_name(self, dt: datetime) -> Optional[str]:
        t = dt.time()
        for name, start, end in self.SESSIONS:
            if start <= t <= end:
                return name
        return None
```

### Phase 2: Dashboard Service

#### 2.1 Architecture
```
services/dashboard/
├── backend/
│   ├── main.py              # FastAPI + WebSocket server
│   ├── ws_manager.py        # WebSocket connection manager
│   ├── redis_subscriber.py  # Subscribe engine_updates
│   └── requirements.txt
├── frontend/
│   ├── package.json         # Next.js / Vite + React
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── CandlestickChart.tsx   # TradingView Lightweight Charts
│   │   │   ├── EquityCurve.tsx
│   │   │   ├── PositionPanel.tsx
│   │   │   ├── TradeHistory.tsx
│   │   │   ├── MetricsCards.tsx       # Win rate, Sharpe, Drawdown
│   │   │   ├── OrderPanel.tsx         # Manual order entry
│   │   │   └── SessionSelector.tsx
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts
│   │   └── lib/
│   │       └── api.ts
│   └── Dockerfile
└── docker-compose.override.yml
```

#### 2.2 Tech stack (validated by research)
- **Charts**: TradingView Lightweight Charts v4.2+ (free, 35KB, Apache 2.0)
- **Frontend**: React + Vite (hoặc Next.js nếu cần SSR)
- **UI**: shadcn/ui + Tailwind CSS
- **Real-time**: WebSocket (FastAPI native) + Redis Pub/Sub bridge
- **State**: Zustand (lightweight) hoặc TanStack Query

#### 2.3 Dashboard Features (MVP)
1. **Candlestick chart** — live price từ market_data channel
2. **Equity curve** — timeseries PnL từ engine
3. **Position panel** — active position, unrealized PnL
4. **Metrics cards** — Win rate, Total PnL, Max Drawdown, Sharpe ratio
5. **Trade history table** — sortable, filterable
6. **Manual order panel** — LONG/SHORT/CLOSE buttons + volume
7. **Session control** — Create/Switch/Reset sessions

### Phase 3: Persistence & Integration

#### 3.1 MySQL Schema (improved from plan)
```sql
CREATE TABLE trading_sessions (
    id VARCHAR(36) PRIMARY KEY,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    strategy VARCHAR(100) DEFAULT 'manual',
    initial_balance DECIMAL(15,2) NOT NULL,
    final_pnl DECIMAL(15,2) DEFAULT 0,
    total_trades INT DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0,
    max_drawdown DECIMAL(5,2) DEFAULT 0,
    sharpe_ratio DECIMAL(8,4) DEFAULT 0,
    total_commission DECIMAL(15,2) DEFAULT 0,
    total_tax DECIMAL(15,2) DEFAULT 0,
    status ENUM('active','completed','cancelled') DEFAULT 'active'
);

CREATE TABLE trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    entry_time DATETIME NOT NULL,
    exit_time DATETIME,
    direction ENUM('LONG','SHORT') NOT NULL,
    volume INT NOT NULL,
    entry_price DECIMAL(10,1) NOT NULL,
    exit_price DECIMAL(10,1),
    slippage_entry DECIMAL(10,2) DEFAULT 0,
    slippage_exit DECIMAL(10,2) DEFAULT 0,
    commission DECIMAL(10,2) DEFAULT 0,
    tax DECIMAL(10,2) DEFAULT 0,
    gross_pnl DECIMAL(10,2),
    net_pnl DECIMAL(10,2),
    status ENUM('open','closed') NOT NULL,
    FOREIGN KEY (session_id) REFERENCES trading_sessions(id)
);

CREATE TABLE equity_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    timestamp DATETIME NOT NULL,
    equity DECIMAL(15,2) NOT NULL,
    pnl_realized DECIMAL(15,2),
    pnl_unrealized DECIMAL(15,2),
    margin_used DECIMAL(15,2),
    margin_available DECIMAL(15,2),
    regime VARCHAR(20),
    session_name VARCHAR(10),  -- ATO/CONT1/CONT2/ATC
    INDEX idx_session_time (session_id, timestamp),
    FOREIGN KEY (session_id) REFERENCES trading_sessions(id)
);
```

### Phase 4: Agent Integration (AFTER exchange is working)
- Subscribe `prediction_votes` / `final_decision`
- Each agent gets its own session_id
- Leaderboard API: compare agent performance
- Tournament mode: multiple agents trade same data simultaneously

---

## PHẦN 3: THỨ TỰ TRIỂN KHAI (Revised)

```
Phase 1: Core Exchange [HIGH PRIORITY]
├── 1a. Tách module structure + config constants
├── 1b. FeeCalculator (đúng VPS/SSI/VSD fees + tax)
├── 1c. MarginManager (17% initial, margin call, price limit ±7%)
├── 1d. Fix rollover (3rd Thursday logic)
├── 1e. Real metrics (win_rate, drawdown, sharpe, equity curve)
├── 1f. Trading session validation
├── 1g. Improved slippage model (volume-dependent)
├── 1h. Multi-session support (SessionManager)
├── 1i. Expand API endpoints + proper error handling
└── 1j. Unit tests for all new modules

Phase 2: Dashboard MVP [HIGH PRIORITY]
├── 2a. Dashboard backend (FastAPI + WebSocket)
├── 2b. Redis → WebSocket bridge (engine_updates channel)
├── 2c. Frontend scaffold (React + Vite + Tailwind)
├── 2d. CandlestickChart (TradingView Lightweight Charts)
├── 2e. EquityCurve + MetricsCards
├── 2f. TradeHistory table + PositionPanel
├── 2g. OrderPanel (manual trading)
└── 2h. Docker integration

Phase 3: Persistence
├── 3a. MySQL schema migration
├── 3b. SQLAlchemy/aiomysql repository layer
├── 3c. Auto-save trades + equity snapshots
└── 3d. Session history + replay

Phase 4: Agent Integration [LATER]
├── 4a. Subscribe prediction_votes channel
├── 4b. Agent session isolation
├── 4c. Leaderboard API
└── 4d. Tournament mode
```

---

## PHẦN 4: RISK NOTES

1. **Fee model phải configurable** — broker khác nhau phí khác nhau, VSD có thể thay đổi
2. **Margin rate thay đổi thường xuyên** — VSD cập nhật ~2 tuần/lần (xem vsd.vn)
3. **Thuế TNCN có thể thay đổi** — theo quy định Bộ Tài chính
4. **Dashboard frontend tech** — nếu team không quen React, có thể dùng Jinja2 SSR + HTMX + Lightweight Charts (simpler stack)
5. **Performance concern** — equity_snapshots mỗi tick → có thể rất lớn, cần sampling strategy (mỗi 1 phút thay vì mỗi tick)
