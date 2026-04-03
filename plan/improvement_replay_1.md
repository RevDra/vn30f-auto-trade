# Replay Engine — Phân Tích Thiếu Sót & Đề Xuất Cải Thiện

> **Service**: `services/replay-engine/`
> **File chính**: `main.py` (305 dòng, 1 class `ReplayEngine`, 2 API endpoints)
> **Ngày phân tích**: 2026-04-02
> **Phân tích bằng**: GitNexus Knowledge Graph (229 nodes, 434 edges)

---

## Mục lục

1. [Tổng quan hiện trạng](#1-tổng-quan-hiện-trạng)
2. [Thiếu sót chi tiết](#2-thiếu-sót-chi-tiết)
3. [Đề xuất cải thiện](#3-đề-xuất-cải-thiện)
4. [Thứ tự triển khai](#4-thứ-tự-triển-khai)

---

## 1. Tổng quan hiện trạng

### 1.1. Kiến trúc hiện tại

```
services/replay-engine/
├── main.py            # 305 lines — toàn bộ logic trong 1 file
├── test_main.py       # 7 unit tests
├── requirements.txt   # numpy, pandas, pydantic-settings, fastapi, uvicorn, redis, pytest
└── Dockerfile         # python:3.11-slim
```

### 1.2. Class ReplayEngine (line 19-174)

| Method | Line | Chức năng |
|--------|------|-----------|
| `__init__` | 20-31 | Khởi tạo state: price, position, pnl, trade_history |
| `execute_order` | 33-51 | Thực thi lệnh với slippage 2-3 ticks (0.2-0.3 điểm) |
| `is_rollover_friday` | 53-62 | Check ngày đáo hạn phái sinh (Thứ 6, ngày 16-22) |
| `inject_rollover_gap` | 64-89 | Mô phỏng roll-over gap ±10-15 điểm |
| `process_tick` | 91-97 | Xử lý 1 tick giá mới |
| `place_order` | 99-164 | Đặt lệnh: open/close/partial close/flip/nhồi lệnh |
| `get_unrealized_pnl` | 166-174 | PnL chưa chốt |

### 1.3. Infrastructure (line 176-305)

| Component | Line | Chức năng |
|-----------|------|-----------|
| `engine` (global) | 176 | Singleton ReplayEngine instance |
| `listen_to_redis` | 180-224 | Subscribe `market_data_vn30f1m`, cập nhật price |
| `lifespan` | 227-256 | Connect Redis, spawn listener |
| `GET /api/v1/pnl` | 260-290 | Dashboard PnL snapshot |
| `POST /api/v1/order` | 292-301 | Manual order placement |

### 1.4. Dependencies

```
replay-engine
├── imports → shared/config.py (Settings: REDIS_HOST, REDIS_PORT)
├── imports → shared/schemas.py (DashboardPnL, SessionSummary, ActivePosition)
├── subscribes → Redis channel "market_data_vn30f1m" (từ data-feed)
└── exposes → HTTP /api/v1/pnl, /api/v1/order
```

### 1.5. Test Coverage hiện tại

| Test | Method được test | Đánh giá |
|------|-----------------|----------|
| `test_execute_order_slippage` | `execute_order` | ✅ Kiểm tra slippage LONG/SHORT |
| `test_execute_order_invalid_action` | `execute_order` | ✅ Edge case invalid action |
| `test_rollover_friday_check` | `is_rollover_friday` | ✅ 3 cases |
| `test_inject_rollover_gap` | `inject_rollover_gap` | ✅ Normal + rollover + consistency + reset |
| `test_place_order_partial_close` | `place_order` | ✅ Partial close |
| `test_place_order_flip` | `place_order` | ✅ Position flip |
| `test_place_order_and_pnl` | `place_order` + `get_unrealized_pnl` | ✅ Full cycle |

---

## 2. Thiếu Sót Chi Tiết

### 2.1. 🔴 CRITICAL — Chưa kết nối vào pipeline tự động

**Vấn đề**: `listen_to_redis()` chỉ cập nhật `engine.current_price`. Không subscribe `prediction_votes` channel → engine không bao giờ tự động trade.

```python
# Hiện tại (line 206-212):
if price > 0:
    new_price = engine.inject_rollover_gap(dt, price)
    engine.current_date = dt
    engine.current_price = new_price
    # (Optional) We could automatically evaluate PnL here, but we will expose an API
```

**Hệ quả**: Toàn bộ pipeline data-feed → quant-regime → replay-engine bị đứt ở khâu cuối. Replay engine chỉ hoạt động khi user gọi `POST /api/v1/order` thủ công.

---

### 2.2. 🔴 CRITICAL — Metrics bị hardcode

**Vấn đề**: `GET /api/v1/pnl` trả về DashboardPnL nhưng nhiều field mock cứng:

```python
# Line 277-281:
summary = SessionSummary(
    total_trades=len(engine.trade_history),
    win_rate=0.0,                    # ❌ HARDCODE — luôn 0%
    pnl_points=engine.total_pnl,
    pnl_vnd=int(engine.total_pnl * 100000),
    max_drawdown_percent=0.0,         # ❌ HARDCODE — luôn 0%
    margin_ratio_current=1.0          # ❌ HARDCODE — luôn 100%
)
```

```python
# Line 289:
timeseries_data=[]                    # ❌ LUÔN RỖNG — dashboard không có dữ liệu chart
```

**Hệ quả**: Dashboard service (khi được phát triển) sẽ không hiển thị được equity curve, win rate, drawdown — những metrics quan trọng nhất cho trading.

---

### 2.3. 🟠 HIGH — Không có persistence

**Vấn đề**: Toàn bộ state nằm trong memory:

```python
# Line 20-26:
self.current_price = 0.0
self.active_position: Optional[Dict[str, Any]] = None
self.total_pnl = 0.0
self.trade_history = []
```

**Hệ quả**:
- Restart container → mất toàn bộ trade history và PnL
- Không thể xem lại kết quả session cũ
- Không thể so sánh hiệu suất giữa các chiến lược
- MySQL đã cấu hình trong docker-compose nhưng chưa được sử dụng

---

### 2.4. 🟠 HIGH — Thiếu phí giao dịch (commission)

**Vấn đề**: `execute_order()` chỉ tính slippage, không tính phí.

**Thực tế VN30F1M**:
- Phí giao dịch: ~4,500 VND/contract/chiều (mở + đóng = 9,000 VND)
- Phí thuế: 0 (phái sinh không chịu thuế)
- 1 điểm VN30F = 100,000 VND → phí ≈ 0.045 điểm/chiều

**Hệ quả**: PnL bị tính lạc quan hơn thực tế. Với scalping (nhiều lệnh nhỏ), chênh lệch có thể rất lớn.

---

### 2.5. 🟠 HIGH — Không quản lý margin

**Vấn đề**: `place_order()` cho phép mở vị thế vô hạn, không kiểm tra margin.

**Thực tế VN30F1M**:
- Ký quỹ ban đầu (Initial Margin): ~17% giá trị hợp đồng
- Ký quỹ duy trì (Maintenance Margin): ~13%
- Giá trị 1 hợp đồng ≈ VN30F index × 100,000 VND
- Ví dụ: VN30F = 1,200 → 1 contract = 120,000,000 VND → margin ≈ 20,400,000 VND

**Hệ quả**: Backtest cho kết quả không thực tế — mở 100 contracts khi account chỉ đủ margin cho 5.

---

### 2.6. 🟡 MEDIUM — Global singleton engine

**Vấn đề**: Line 176 tạo 1 instance duy nhất:

```python
engine = ReplayEngine()
```

**Hệ quả**:
- Không thể chạy nhiều backtest session cùng lúc
- Không thể so sánh chiến lược A vs B đồng thời
- Reset bằng cách restart service → mất data

---

### 2.7. 🟡 MEDIUM — Slippage model quá đơn giản

**Vấn đề**: Slippage cố định 2-3 ticks cho mọi trường hợp:

```python
# Line 43:
slippage_ticks = random.randint(2, 3)
```

**Thực tế**:
- Slippage phụ thuộc volume (1 contract ≠ 10 contracts)
- Slippage phụ thuộc thanh khoản tại thời điểm (ATO/ATC có thanh khoản cao hơn)
- Slippage phụ thuộc biến động (VIX cao → slippage cao)
- Volume lớn có thể hit nhiều price level (market impact)

---

### 2.8. 🟡 MEDIUM — Rollover logic không chính xác 100%

**Vấn đề**: `is_rollover_friday` check cứng ngày 16-22:

```python
# Line 59-61:
if date.weekday() == 4:  # Thứ 6
    if 16 <= date.day <= 22:
        return True
```

**Thực tế**: Ngày đáo hạn VN30F là Thứ 5 **thứ 3 trong tháng**, không phải lúc nào cũng rơi vào ngày 16-22. Nếu tháng bắt đầu bằng Thứ 6, Thứ 5 thứ 3 rơi vào ngày 15 → Thứ 6 sau đó là ngày 16. Nhưng nếu tháng bắt đầu bằng Thứ 5, Thứ 5 thứ 3 rơi vào ngày 21 → Thứ 6 sau đó là ngày 22. Logic hiện tại **gần đúng** nhưng có edge cases sai.

---

### 2.9. 🟡 MEDIUM — API thiếu endpoints quan trọng

**Hiện có**: 2 endpoints
- `GET /api/v1/pnl` — snapshot PnL
- `POST /api/v1/order` — đặt lệnh thủ công

**Thiếu**:
- Không có endpoint xem trade history
- Không có endpoint xem equity curve theo thời gian
- Không có endpoint reset engine
- Không có endpoint force close position
- Không có health check endpoint
- Không có WebSocket cho real-time updates

---

### 2.10. 🟡 MEDIUM — Error handling yếu

**`POST /api/v1/order` (line 292-301)**:

```python
def place_order(action: str, volume: int):
    try:
        engine.place_order(action.upper(), volume)
        return {"status": "ok", ...}
    except Exception as e:
        return {"status": "error", "message": str(e)}  # ❌ Luôn trả 200 OK
```

**Vấn đề**:
- Error luôn trả HTTP 200 — client không phân biệt được success/failure qua status code
- Không validate input (volume <= 0? volume = 999999?)
- Không có request/response schema (Pydantic model)

---

### 2.11. 🟢 LOW — Thiếu test coverage cho API layer

**Chưa test**:
- `listen_to_redis()` — Redis subscriber
- `lifespan()` — app lifecycle
- `GET /api/v1/pnl` — API endpoint
- `POST /api/v1/order` — API endpoint
- `process_tick()` — tick processing
- Edge cases: đặt lệnh khi chưa có price (current_price = 0.0)

---

### 2.12. 🟢 LOW — Code structure: monolithic single file

**305 dòng** gồm:
- Business logic (ReplayEngine class)
- Infrastructure (Redis connection)
- API layer (FastAPI endpoints)
- App bootstrap

Tất cả trong 1 file → khó maintain khi service phát triển.

---

### 2.13. 🟢 LOW — `last_trade_time` không được init trong `__init__`

```python
# Line 128 — sử dụng getattr fallback:
"entry_time": getattr(self, "last_trade_time", self.current_date),

# Line 164 — set sau khi place_order:
self.last_trade_time = self.current_date
```

**Vấn đề**: `last_trade_time` chỉ tồn tại sau lần `place_order` đầu tiên. Lần đầu dùng `getattr` fallback — hoạt động nhưng implicit và dễ gây nhầm lẫn.

---

## 3. Đề Xuất Cải Thiện

### 3.1. [P0] Subscribe `prediction_votes` / `final_decision`

**Mục tiêu**: Replay engine tự động trade theo tín hiệu từ quant-regime (hoặc adjudicator khi có).

**Chi tiết thay đổi**:

```python
# Thêm listener mới cho prediction_votes channel
async def listen_to_predictions():
    """Subscribe prediction_votes → auto place_order"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("prediction_votes")

    async for message in pubsub.listen():
        if message["type"] == "message":
            vote = json.loads(message["data"])
            action = vote.get("action")         # "LONG" / "SHORT" / "HOLD"
            confidence = vote.get("confidence")  # 0.0 - 1.0
            volume = vote.get("volume", 1)

            if action in ["LONG", "SHORT"] and confidence >= CONFIDENCE_THRESHOLD:
                engine.place_order(action, volume)
            elif action == "HOLD":
                pass  # Giữ nguyên vị thế
```

**Cần thêm**: Configurable `CONFIDENCE_THRESHOLD` trong `shared/config.py`.

**Impact**: Không ảnh hưởng service khác. Chỉ thêm code mới trong replay-engine.

---

### 3.2. [P0] Tính toán metrics thực tế

**Mục tiêu**: `win_rate`, `max_drawdown_percent`, `timeseries_data` được tính từ dữ liệu thực.

**Chi tiết**:

```python
def calculate_win_rate(self) -> float:
    """Tính win rate từ trade_history"""
    if not self.trade_history:
        return 0.0
    wins = sum(1 for t in self.trade_history if t["pnl"] > 0)
    return round(wins / len(self.trade_history) * 100, 2)

def calculate_max_drawdown(self) -> float:
    """Tính max drawdown % từ equity curve"""
    if not self.equity_curve:
        return 0.0
    peak = self.equity_curve[0]
    max_dd = 0.0
    for equity in self.equity_curve:
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return round(max_dd, 2)
```

**Cần thêm** vào `__init__`:
- `self.equity_curve: List[float] = []` — track equity mỗi tick
- `self.timeseries_pnl: List[dict] = []` — track PnL + regime theo thời gian
- Cập nhật `self.initial_balance` config

**Impact**: Thay đổi `get_pnl()` response (cùng schema, dữ liệu thực thay vì mock). Không cần sửa shared/schemas.py.

---

### 3.3. [P1] Commission & Fee model

**Mục tiêu**: Trừ phí giao dịch vào PnL, kết quả backtest sát thực tế.

**Chi tiết**:

```python
# Thêm vào __init__:
self.commission_per_contract = 0.045  # 4,500 VND ≈ 0.045 điểm VN30F

# Thêm vào place_order, sau khi tính PnL:
commission = self.commission_per_contract * close_vol * 2  # 2 chiều (mở + đóng)
pnl -= commission
self.total_commission += commission
```

**Config cần thêm** (shared/config.py hoặc replay-engine local):
```
COMMISSION_PER_CONTRACT_VND: int = 4500
POINT_VALUE_VND: int = 100000
```

---

### 3.4. [P1] Margin management

**Mục tiêu**: Giới hạn vị thế theo margin thực tế, prevent over-leveraging.

**Chi tiết**:

```python
# Thêm vào __init__:
self.account_balance = 100_000_000     # 100M VND (default)
self.initial_margin_rate = 0.17        # 17% ký quỹ ban đầu
self.maintenance_margin_rate = 0.13    # 13% ký quỹ duy trì
self.point_value = 100_000             # 1 điểm = 100k VND

# Thêm method:
def get_required_margin(self, volume: int) -> float:
    """Tính margin cần thiết cho volume contracts"""
    contract_value = self.current_price * self.point_value
    return contract_value * self.initial_margin_rate * volume

def can_open_position(self, volume: int) -> bool:
    """Kiểm tra đủ margin để mở vị thế"""
    required = self.get_required_margin(volume)
    available = self.account_balance - self.get_used_margin() + self.total_pnl * self.point_value
    return available >= required

# Thêm check vào place_order:
if not self.can_open_position(volume):
    raise InsufficientMarginError(f"Need {required:,.0f} VND, available {available:,.0f} VND")
```

**Config cần thêm**:
```
INITIAL_BALANCE_VND: int = 100_000_000
INITIAL_MARGIN_RATE: float = 0.17
MAINTENANCE_MARGIN_RATE: float = 0.13
```

---

### 3.5. [P1] Persistence — MySQL integration

**Mục tiêu**: Lưu trade history & session state vào MySQL, survive restart.

**Schema MySQL**:

```sql
CREATE TABLE trading_sessions (
    id          VARCHAR(36) PRIMARY KEY,  -- UUID
    started_at  DATETIME NOT NULL,
    ended_at    DATETIME,
    strategy    VARCHAR(100),
    initial_balance DECIMAL(15,2),
    final_pnl   DECIMAL(15,2),
    total_trades INT,
    win_rate     DECIMAL(5,2),
    max_drawdown DECIMAL(5,2),
    status       ENUM('active', 'completed', 'cancelled')
);

CREATE TABLE trades (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    session_id   VARCHAR(36) NOT NULL,
    entry_time   DATETIME NOT NULL,
    exit_time    DATETIME,
    type         ENUM('LONG', 'SHORT') NOT NULL,
    volume       INT NOT NULL,
    entry_price  DECIMAL(10,2) NOT NULL,
    exit_price   DECIMAL(10,2),
    commission   DECIMAL(10,2) DEFAULT 0,
    pnl          DECIMAL(10,2),
    status       ENUM('open', 'closed') NOT NULL,
    FOREIGN KEY (session_id) REFERENCES trading_sessions(id)
);

CREATE TABLE equity_snapshots (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    session_id   VARCHAR(36) NOT NULL,
    timestamp    DATETIME NOT NULL,
    equity       DECIMAL(15,2) NOT NULL,
    pnl_realized DECIMAL(15,2),
    pnl_unrealized DECIMAL(15,2),
    regime       VARCHAR(20),
    INDEX idx_session_time (session_id, timestamp),
    FOREIGN KEY (session_id) REFERENCES trading_sessions(id)
);
```

**Dependencies**: `sqlalchemy`, `aiomysql` → thêm vào requirements.txt.

---

### 3.6. [P2] Cải thiện slippage model

**Mục tiêu**: Slippage phản ánh thực tế hơn (volume-dependent, volatility-aware).

```python
def calculate_slippage(self, action: str, volume: int) -> float:
    """
    Dynamic slippage model:
    - Base: 2 ticks
    - Volume impact: +1 tick per 5 contracts
    - Rollover day: +2 ticks (thanh khoản thấp hơn khi chuyển hợp đồng)
    """
    base_ticks = 2
    volume_impact = volume // 5       # +1 tick per 5 contracts
    rollover_impact = 2 if self.is_rollover_friday(self.current_date) else 0

    total_ticks = base_ticks + volume_impact + rollover_impact
    return total_ticks * self.tick_size
```

---

### 3.7. [P2] Fix rollover date calculation

**Mục tiêu**: Tính chính xác ngày đáo hạn theo calendar thật.

```python
def get_third_thursday(self, year: int, month: int) -> datetime:
    """Tính Thứ 5 tuần thứ 3 trong tháng (ngày đáo hạn phái sinh VN30F)"""
    # Ngày 1 của tháng
    first_day = datetime(year, month, 1)
    # Tìm Thứ 5 đầu tiên
    days_until_thursday = (3 - first_day.weekday()) % 7
    first_thursday = first_day + timedelta(days=days_until_thursday)
    # Thứ 5 thứ 3 = Thứ 5 đầu tiên + 14 ngày
    third_thursday = first_thursday + timedelta(days=14)
    return third_thursday

def is_rollover_friday(self, date: datetime) -> bool:
    """Thứ 6 ngay sau ngày đáo hạn"""
    third_thu = self.get_third_thursday(date.year, date.month)
    rollover_friday = third_thu + timedelta(days=1)
    return date.date() == rollover_friday.date()
```

---

### 3.8. [P2] Mở rộng API endpoints

```python
@app.get("/health")
def health():
    return {"status": "ok", "redis": redis_client is not None}

@app.get("/api/v1/trades")
def get_trades(limit: int = 50, offset: int = 0):
    """Xem trade history với pagination"""
    trades = engine.trade_history[offset:offset+limit]
    return {"trades": trades, "total": len(engine.trade_history)}

@app.get("/api/v1/equity-curve")
def get_equity_curve():
    """Equity curve data cho charting"""
    return {"data": engine.timeseries_pnl}

@app.post("/api/v1/close-position")
def force_close():
    """Force close vị thế hiện tại"""
    if engine.active_position:
        pos_type = engine.active_position["type"]
        close_action = "SHORT" if pos_type == "LONG" else "LONG"
        engine.place_order(close_action, engine.active_position["volume"])
        return {"status": "closed"}
    return {"status": "no_position"}

@app.post("/api/v1/reset")
def reset_engine():
    """Reset engine state cho session mới"""
    global engine
    engine = ReplayEngine()
    return {"status": "reset"}
```

---

### 3.9. [P2] Cải thiện error handling & input validation

```python
from pydantic import BaseModel, Field
from fastapi import HTTPException

class OrderRequest(BaseModel):
    action: str = Field(..., pattern="^(LONG|SHORT)$")
    volume: int = Field(..., gt=0, le=100)

@app.post("/api/v1/order", status_code=201)
def place_order(order: OrderRequest):
    try:
        engine.place_order(order.action, order.volume)
        return {
            "status": "ok",
            "action": order.action,
            "volume": order.volume,
            "exec_price": engine.active_position["entry_price"] if engine.active_position else None,
            "total_pnl": engine.total_pnl
        }
    except InsufficientMarginError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

### 3.10. [P3] Tách file — Module structure

```
services/replay-engine/
├── main.py              # FastAPI app, lifespan, routes
├── engine.py            # class ReplayEngine (core business logic)
├── models.py            # Request/Response Pydantic models
├── listeners.py         # Redis subscribers (market_data, prediction_votes)
├── persistence.py       # MySQL repository (save/load trades)
├── margin.py            # Margin calculation logic
├── config.py            # Local config (commission, margin rates)
├── tests/
│   ├── test_engine.py       # Unit tests cho ReplayEngine
│   ├── test_api.py          # Integration tests cho API endpoints
│   ├── test_listeners.py    # Tests cho Redis subscribers
│   └── test_margin.py       # Tests cho margin logic
├── requirements.txt
└── Dockerfile
```

---

### 3.11. [P3] Multi-session support

```python
# Thay singleton bằng session manager
class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, ReplayEngine] = {}
        self.active_session_id: Optional[str] = None

    def create_session(self, strategy: str = "default", balance: float = 100_000_000) -> str:
        session_id = str(uuid.uuid4())
        engine = ReplayEngine(initial_balance=balance, strategy=strategy)
        self.sessions[session_id] = engine
        self.active_session_id = session_id
        return session_id

    def get_active_engine(self) -> ReplayEngine:
        if not self.active_session_id:
            raise NoActiveSessionError()
        return self.sessions[self.active_session_id]
```

---

### 3.12. [P3] Bổ sung test coverage

**Tests cần thêm**:

| Test | Mô tả |
|------|--------|
| `test_process_tick` | Verify price update + rollover gap |
| `test_place_order_same_direction` | Nhồi lệnh cùng chiều → avg price |
| `test_place_order_zero_price` | Edge case: đặt lệnh khi price = 0 |
| `test_win_rate_calculation` | Win rate chính xác sau N trades |
| `test_max_drawdown` | Drawdown tính đúng từ equity curve |
| `test_commission_deduction` | PnL trừ đúng commission |
| `test_margin_check` | Từ chối lệnh khi không đủ margin |
| `test_api_pnl_response` | GET /api/v1/pnl trả đúng schema |
| `test_api_order_validation` | POST /api/v1/order reject invalid input |
| `test_api_order_returns_4xx` | Error trả proper HTTP status code |
| `test_listen_to_redis` | Mock Redis → verify price update |
| `test_listen_to_predictions` | Mock votes → verify auto place_order |
| `test_persistence_save_load` | Save trade → restart → load lại đúng |
| `test_rollover_edge_cases` | Tháng bắt đầu bằng thứ 5 hoặc thứ 6 |

---

## 4. Thứ Tự Triển Khai

```
Phase 1 — Kết nối pipeline (ưu tiên cao nhất)
├── 3.1  Subscribe prediction_votes        [P0] ~2h
├── 3.2  Tính metrics thực tế              [P0] ~3h
└── 3.9  Fix error handling                [P2] ~1h
    → Kết quả: engine tự động trade, metrics thật, API proper

Phase 2 — Realistic simulation
├── 3.3  Commission & fee                  [P1] ~1h
├── 3.4  Margin management                 [P1] ~3h
├── 3.6  Dynamic slippage                  [P2] ~1h
└── 3.7  Fix rollover calculation          [P2] ~1h
    → Kết quả: backtest sát thực tế VN30F

Phase 3 — Persistence & API
├── 3.5  MySQL integration                 [P1] ~4h
├── 3.8  Mở rộng API endpoints             [P2] ~2h
└── 3.12 Bổ sung tests                     [P3] ~3h
    → Kết quả: data không mất, API đầy đủ, test coverage

Phase 4 — Architecture
├── 3.10 Tách file structure               [P3] ~2h
└── 3.11 Multi-session support             [P3] ~3h
    → Kết quả: codebase scalable, so sánh chiến lược

Tổng: ~26h chia 4 phases, mỗi phase có thể ship độc lập.
```

### Cross-service impact

| Thay đổi | Impact services khác? |
|----------|----------------------|
| Subscribe prediction_votes | ❌ Không — chỉ thêm subscriber |
| Fix metrics | ❌ Không — cùng DashboardPnL schema |
| Commission, margin, slippage | ❌ Không — internal logic |
| MySQL persistence | ❌ Không — MySQL đã sẵn trong docker-compose |
| Mở rộng API | ❌ Không — thêm endpoints mới |
| Sửa shared/config.py | ⚠️ Có thể — nếu thêm config fields (backward compatible) |

> **Mọi thay đổi đều backward compatible và không ảnh hưởng data-feed, quant-regime hay các service khác.**
