"""Core ReplayEngine — refactored with proper fees, margin, slippage, metrics."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from calendar import monthrange

from app.constants import CONTRACT_MULTIPLIER, DEFAULT_INITIAL_BALANCE, TICK_SIZE
from app.fees import FeeCalculator
from app.risk import MarginManager, InsufficientMarginError
from app.metrics import MetricTracker
from app.session_validator import TradingSessionValidator
from app.slippage import SlippageModel

logger = logging.getLogger("replay-engine")


def get_expiry_date(year: int, month: int) -> datetime:
    """Calculate the 3rd Thursday of a given month (VN30F expiry date)."""
    first_day_weekday = datetime(year, month, 1).weekday()
    # weekday: Monday=0 ... Thursday=3
    # First Thursday of the month
    first_thursday = 1 + (3 - first_day_weekday) % 7
    third_thursday = first_thursday + 14
    return datetime(year, month, third_thursday)


def is_rollover_friday(date: datetime) -> bool:
    """Check if date is the Friday after VN30F expiry (3rd Thursday)."""
    if date.weekday() != 4:  # Not Friday
        return False
    expiry = get_expiry_date(date.year, date.month)
    # Rollover Friday = expiry + 1 day
    return date.date() == (expiry + __import__("datetime").timedelta(days=1)).date()


class ReplayEngine:
    """Mock exchange engine for VN30F futures simulation."""

    def __init__(
        self,
        session_id: str = "default",
        initial_balance: float = DEFAULT_INITIAL_BALANCE,
        strategy: str = "manual",
        strict_hours: bool = False,
    ):
        self.session_id = session_id
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.current_price = 0.0
        self.reference_price = 0.0
        self.current_date = datetime.now()

        self.active_position: Optional[Dict[str, Any]] = None
        self.total_pnl = 0.0
        self.total_commission = 0.0
        self.total_tax = 0.0
        self.trade_history: List[Dict] = []

        # Rollover state
        self._rollover_date: Optional[str] = None
        self._rollover_gap: float = 0.0

        # Sub-modules
        self.fee_calc = FeeCalculator()
        self.margin_mgr = MarginManager()
        self.metrics = MetricTracker(initial_balance)
        self.session_validator = TradingSessionValidator(strict=strict_hours)
        self.slippage = SlippageModel()

    @property
    def equity(self) -> float:
        """Current equity = balance + unrealized PnL."""
        return self.balance + self.get_unrealized_pnl()

    def get_unrealized_pnl(self) -> float:
        if not self.active_position:
            return 0.0
        pos = self.active_position
        price_diff = self.current_price - pos["entry_price"]
        if pos["type"] == "SHORT":
            price_diff = -price_diff
        return price_diff * pos["volume"] * CONTRACT_MULTIPLIER

    def process_tick(self, timestamp: str, price: float, regime: str = "unknown"):
        """Process one market data tick."""
        dt = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        self.current_date = dt
        self.current_price = self._apply_rollover_gap(dt, price)

        # Update reference price at start of day
        if not hasattr(self, "_last_ref_date") or self._last_ref_date != dt.date():
            self.reference_price = price
            self._last_ref_date = dt.date()

        # Update metrics with current equity
        self.metrics.update_equity(self.equity, dt, regime)

    def _apply_rollover_gap(self, dt: datetime, price: float) -> float:
        """Simulate rollover gap on expiry Friday."""
        if is_rollover_friday(dt):
            date_str = dt.strftime("%Y-%m-%d")
            if self._rollover_date != date_str:
                self._rollover_date = date_str
                import random
                gap = random.uniform(10.0, 15.0) * random.choice([1, -1])
                self._rollover_gap = gap
                logger.info(f"Rollover gap {date_str}: {gap:.2f}")
            return round(price + self._rollover_gap, 2)
        else:
            if self._rollover_date is not None:
                self._rollover_date = None
                self._rollover_gap = 0.0
        return round(price, 2)

    def place_order(self, action: str, volume: int) -> dict:
        """Place an order with full validation and fee calculation.

        Returns trade result dict on success, raises on failure.
        """
        if action not in ("LONG", "SHORT"):
            raise ValueError(f"Invalid action: {action}")
        if volume <= 0:
            raise ValueError(f"Invalid volume: {volume}")

        # Session validation
        allowed, session_name, msg = self.session_validator.validate_order_time(
            self.current_date
        )
        if not allowed:
            raise ValueError(msg)

        # Determine if this is a rollover day for slippage
        _is_rollover = is_rollover_friday(self.current_date)

        # Calculate execution price with slippage
        exec_price = self.slippage.calculate_slippage(
            action,
            self.current_price,
            volume,
            session_name=session_name or "CONT1",
            is_rollover=_is_rollover,
        )

        if self.active_position is None:
            # Opening new position — check margin
            existing_vol = 0
            self.margin_mgr.validate_order(
                equity=self.equity,
                price=exec_price,
                volume=volume,
                existing_volume=existing_vol,
                ref_price=self.reference_price,
            )

            # Calculate and deduct entry fees
            entry_fees = self.fee_calc.calculate_one_side(exec_price, volume)
            self.balance -= entry_fees.total
            self.total_commission += (
                entry_fees.broker_fee + entry_fees.exchange_fee + entry_fees.clearing_fee
            )
            self.total_tax += entry_fees.tax

            self.active_position = {
                "type": action,
                "volume": volume,
                "entry_price": exec_price,
                "entry_time": self.current_date,
            }
            return {
                "action": "OPEN",
                "type": action,
                "volume": volume,
                "exec_price": exec_price,
                "fees": entry_fees.total,
            }

        pos = self.active_position
        if pos["type"] == action:
            # Adding to existing position — check margin for total
            total_vol = pos["volume"] + volume
            self.margin_mgr.validate_order(
                equity=self.equity,
                price=exec_price,
                volume=volume,
                existing_volume=pos["volume"],
                ref_price=self.reference_price,
            )

            entry_fees = self.fee_calc.calculate_one_side(exec_price, volume)
            self.balance -= entry_fees.total
            self.total_commission += (
                entry_fees.broker_fee + entry_fees.exchange_fee + entry_fees.clearing_fee
            )
            self.total_tax += entry_fees.tax

            avg_price = (
                (pos["entry_price"] * pos["volume"]) + (exec_price * volume)
            ) / total_vol
            self.active_position = {
                "type": action,
                "volume": total_vol,
                "entry_price": round(avg_price, 2),
                "entry_time": pos["entry_time"],
            }
            return {
                "action": "ADD",
                "type": action,
                "volume": volume,
                "total_volume": total_vol,
                "exec_price": exec_price,
                "avg_price": round(avg_price, 2),
                "fees": entry_fees.total,
            }

        # Closing (opposite direction)
        close_vol = min(pos["volume"], volume)
        entry = pos["entry_price"]

        # Calculate gross PnL in points then VND
        if pos["type"] == "LONG":
            pnl_points = (exec_price - entry) * close_vol
        else:
            pnl_points = (entry - exec_price) * close_vol

        gross_pnl = pnl_points * CONTRACT_MULTIPLIER

        # Exit fees
        exit_fees = self.fee_calc.calculate_one_side(exec_price, close_vol)
        net_pnl = gross_pnl - exit_fees.total

        self.balance += gross_pnl - exit_fees.total
        self.total_pnl += net_pnl
        self.total_commission += (
            exit_fees.broker_fee + exit_fees.exchange_fee + exit_fees.clearing_fee
        )
        self.total_tax += exit_fees.tax

        trade_record = {
            "entry_time": pos["entry_time"].isoformat()
            if isinstance(pos["entry_time"], datetime)
            else str(pos["entry_time"]),
            "exit_time": self.current_date.isoformat()
            if isinstance(self.current_date, datetime)
            else str(self.current_date),
            "type": pos["type"],
            "volume": close_vol,
            "entry_price": entry,
            "exit_price": exec_price,
            "gross_pnl": round(gross_pnl, 2),
            "commission": round(
                exit_fees.broker_fee + exit_fees.exchange_fee + exit_fees.clearing_fee, 2
            ),
            "tax": round(exit_fees.tax, 2),
            "net_pnl": round(net_pnl, 2),
        }
        self.trade_history.append(trade_record)

        remaining = pos["volume"] - close_vol
        if remaining > 0:
            self.active_position["volume"] = remaining
        else:
            self.active_position = None

        result = {
            "action": "CLOSE",
            "type": pos["type"],
            "volume": close_vol,
            "exec_price": exec_price,
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "fees": exit_fees.total,
        }

        # Handle flip (remaining volume opens new position)
        flip_vol = volume - close_vol
        if flip_vol > 0:
            flip_fees = self.fee_calc.calculate_one_side(exec_price, flip_vol)
            self.balance -= flip_fees.total
            self.total_commission += (
                flip_fees.broker_fee + flip_fees.exchange_fee + flip_fees.clearing_fee
            )
            self.total_tax += flip_fees.tax

            self.active_position = {
                "type": action,
                "volume": flip_vol,
                "entry_price": exec_price,
                "entry_time": self.current_date,
            }
            result["flip"] = {
                "type": action,
                "volume": flip_vol,
                "exec_price": exec_price,
            }

        return result

    def close_position(self) -> Optional[dict]:
        """Force close the entire active position."""
        if not self.active_position:
            return None
        opposite = "SHORT" if self.active_position["type"] == "LONG" else "LONG"
        return self.place_order(opposite, self.active_position["volume"])

    def reset(self):
        """Reset engine to initial state."""
        self.__init__(
            session_id=self.session_id,
            initial_balance=self.initial_balance,
            strategy=self.strategy,
            strict_hours=self.session_validator.strict,
        )

    def get_state(self) -> dict:
        """Full engine state snapshot."""
        return {
            "session_id": self.session_id,
            "strategy": self.strategy,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_commission": round(self.total_commission, 2),
            "total_tax": round(self.total_tax, 2),
            "current_price": self.current_price,
            "active_position": self.active_position,
            "total_trades": len(self.trade_history),
            "win_rate": self.metrics.calculate_win_rate(self.trade_history),
            "max_drawdown": self.metrics.calculate_max_drawdown(),
            "sharpe_ratio": self.metrics.calculate_sharpe_ratio(),
        }
