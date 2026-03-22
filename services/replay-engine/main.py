import random
import logging
from datetime import datetime, timedelta
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI
from contextlib import asynccontextmanager
import redis.asyncio as redis

import sys
sys.path.append("/app")
from shared.config import settings
from shared.schemas import DashboardPnL, SessionSummary, ActivePosition

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("replay-engine")

class ReplayEngine:
    def __init__(self):
        self.current_price = 0.0
        self.current_date = datetime.now()
        # Active position: None or Dict with 'type' (LONG/SHORT), 'volume', 'entry_price'
        self.active_position: Optional[Dict[str, Any]] = None
        self.total_pnl = 0.0
        self.trade_history = []

        self.tick_size = 0.1 # 0.1 điểm VN30F1M

        self.current_rollover_date: Optional[str] = None
        self.current_rollover_gap: float = 0.0

    def execute_order(self, action: str, volume: int, current_price: float) -> float:
        """
        Thực thi lệnh với mô phỏng trượt giá (slippage).
        - Slippage: 2-3 ticks (0.2 - 0.3 điểm).
        - LONG: mua đắt hơn (cộng slippage).
        - SHORT: bán rẻ hơn (trừ slippage).
        """
        if action not in ["LONG", "SHORT"]:
            raise ValueError(f"Invalid action: {action}")

        slippage_ticks = random.randint(2, 3)
        slippage_amount = slippage_ticks * self.tick_size

        if action == "LONG":
            executed_price = current_price + slippage_amount
        else:
            executed_price = current_price - slippage_amount

        return round(executed_price, 2)

    def is_rollover_friday(self, date: datetime) -> bool:
        """
        Kiểm tra xem ngày hiện tại có phải là thứ 6 sau ngày đáo hạn phái sinh không.
        Ngày đáo hạn là Thứ 5 tuần thứ 3 trong tháng.
        Thứ 6 sau đó sẽ là ngày tiếp theo, tức là Thứ 6 thuộc khoảng ngày từ 16 đến 22.
        """
        if date.weekday() == 4: # Thứ 6
            if 16 <= date.day <= 22:
                return True
        return False

    def inject_rollover_gap(self, current_date: datetime, price: float) -> float:
        """
        Mô phỏng Roll-over Gap:
        Cộng/trừ ngẫu nhiên 10-15 điểm vào giá mô phỏng nếu là sáng Thứ 6 tuần đáo hạn.
        Đảm bảo gap được cộng nhất quán (1 giá trị cố định) cho toàn bộ phiên ngày thứ 6 đó.
        """
        if self.is_rollover_friday(current_date):
            date_str = current_date.strftime("%Y-%m-%d")

            # Khởi tạo gap cho ngày mới nếu chưa có
            if self.current_rollover_date != date_str:
                self.current_rollover_date = date_str
                gap = random.uniform(10.0, 15.0)
                direction = random.choice([1, -1])
                self.current_rollover_gap = gap * direction
                logger.info(f"Initialized Rollover Gap for {date_str}: {self.current_rollover_gap:.2f}")

            new_price = price + self.current_rollover_gap
            return round(new_price, 2)
        else:
            # Reset gap khi qua ngày khác
            if self.current_rollover_date is not None:
                self.current_rollover_date = None
                self.current_rollover_gap = 0.0

        return round(price, 2)

    def process_tick(self, timestamp: str, price: float):
        """
        Xử lý 1 tick giá mới từ thị trường
        """
        dt = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        self.current_date = dt
        self.current_price = self.inject_rollover_gap(dt, price)

    def place_order(self, action: str, volume: int):
        """
        Mô phỏng đặt lệnh và cập nhật PnL.
        """
        exec_price = self.execute_order(action, volume, self.current_price)

        if self.active_position is None:
            self.active_position = {
                "type": action,
                "volume": volume,
                "entry_price": exec_price
            }
            logger.info(f"Opened {action} position: {volume} @ {exec_price}")
        else:
            pos_type = self.active_position["type"]
            entry = self.active_position["entry_price"]
            current_vol = self.active_position["volume"]

            if pos_type != action:
                # Đóng vị thế (một phần hoặc toàn bộ)
                close_vol = min(current_vol, volume)

                if pos_type == "LONG":
                    pnl = (exec_price - entry) * close_vol
                else:
                    pnl = (entry - exec_price) * close_vol

                self.total_pnl += pnl
                self.trade_history.append({
                    "entry_time": getattr(self, "last_trade_time", self.current_date),
                    "exit_time": self.current_date,
                    "type": pos_type,
                    "volume": close_vol,
                    "entry_price": entry,
                    "exit_price": exec_price,
                    "pnl": round(pnl, 2)
                })
                logger.info(f"Closed {close_vol} of {pos_type} position: PnL = {round(pnl, 2)}")

                remaining_vol = current_vol - close_vol
                if remaining_vol > 0:
                    self.active_position["volume"] = remaining_vol
                else:
                    self.active_position = None

                # Nếu volume yêu cầu đóng lớn hơn volume đang giữ -> Mở vị thế mới ngược lại (flip)
                new_pos_vol = volume - close_vol
                if new_pos_vol > 0:
                    self.active_position = {
                        "type": action,
                        "volume": new_pos_vol,
                        "entry_price": exec_price
                    }
                    logger.info(f"Flipped position to {action}: {new_pos_vol} @ {exec_price}")
            else:
                # Nhồi lệnh cùng chiều (cộng dồn volume và tính giá trung bình)
                total_vol = current_vol + volume
                avg_price = ((entry * current_vol) + (exec_price * volume)) / total_vol
                self.active_position = {
                    "type": action,
                    "volume": total_vol,
                    "entry_price": round(avg_price, 2)
                }
                logger.info(f"Added to {action} position: {volume} @ {exec_price}. New Avg: {round(avg_price, 2)}")

        self.last_trade_time = self.current_date

    def get_unrealized_pnl(self) -> float:
        if not self.active_position:
            return 0.0

        pos = self.active_position
        if pos["type"] == "LONG":
            return (self.current_price - pos["entry_price"]) * pos["volume"]
        else:
            return (pos["entry_price"] - self.current_price) * pos["volume"]

engine = ReplayEngine()
redis_client = None
background_tasks = set()

async def listen_to_redis():
    """
    Background task to listen to Redis Pub/Sub for market data
    """
    if not redis_client:
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("market_data_vn30f1m")

    logger.info("Subscribed to Redis channel 'market_data_vn30f1m'")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])

                    timestamp_str = data.get("timestamp")
                    if timestamp_str:
                        dt = datetime.fromisoformat(timestamp_str)
                    else:
                        dt = datetime.now()

                    price = float(data.get("close", 0.0))

                    if price > 0:
                        # Process tick and simulate gap if applicable
                        new_price = engine.inject_rollover_gap(dt, price)
                        engine.current_date = dt
                        engine.current_price = new_price

                        logger.info(f"Processed tick {dt}: {price} -> Engine Price: {new_price}")

                        # (Optional) We could automatically evaluate PnL here, but we will expose an API

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
    except asyncio.CancelledError:
        logger.info("Redis listener cancelled")
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
    finally:
        await pubsub.unsubscribe("market_data_vn30f1m")
        await pubsub.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, background_tasks

    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
        await redis_client.ping()
        logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")

        # Start the listener task
        task = asyncio.create_task(listen_to_redis())
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None

    yield

    # Cleanup
    for task in background_tasks:
        task.cancel()

    if redis_client:
        await redis_client.close()

app = FastAPI(title="Replay Engine (Mock Exchange)", version="1.0.0", lifespan=lifespan)

@app.get("/api/v1/pnl")
def get_pnl() -> DashboardPnL:
    """
    Returns the PnL snapshot matching DashboardPnL schema.
    """
    active_pos = None
    if engine.active_position:
        active_pos = ActivePosition(
            type=engine.active_position["type"],
            volume=engine.active_position["volume"],
            entry_price=engine.active_position["entry_price"],
            current_price=engine.current_price,
            unrealized_pnl=engine.get_unrealized_pnl()
        )

    summary = SessionSummary(
        total_trades=len(engine.trade_history),
        win_rate=0.0, # Not calculating full win rate for simplicity
        pnl_points=engine.total_pnl,
        pnl_vnd=int(engine.total_pnl * 100000), # 1 điểm = 100k
        max_drawdown_percent=0.0,
        margin_ratio_current=1.0 # Mock
    )

    return DashboardPnL(
        timestamp=datetime.now(),
        symbol="VN30F1M",
        session_summary=summary,
        active_position=active_pos,
        timeseries_data=[]
    )

@app.post("/api/v1/order")
def place_order(action: str, volume: int):
    """
    Test endpoint to simulate placing an order on the replay engine.
    """
    try:
        engine.place_order(action.upper(), volume)
        return {"status": "ok", "action": action.upper(), "volume": volume, "exec_price": engine.active_position["entry_price"] if engine.active_position else None}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
