"""Real-time metrics calculator: win rate, drawdown, Sharpe ratio, equity curve."""

import math
from typing import List, Optional
from datetime import datetime


class MetricTracker:
    """Tracks and calculates trading performance metrics in real time."""

    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        self.equity_curve: List[float] = [initial_balance]
        self.peak_equity: float = initial_balance
        self.max_drawdown: float = 0.0
        self.returns: List[float] = []
        self.timeseries: List[dict] = []

    def update_equity(
        self,
        new_equity: float,
        timestamp: Optional[datetime] = None,
        regime: str = "unknown",
    ):
        """Record a new equity value and update drawdown."""
        self.equity_curve.append(new_equity)

        if new_equity > self.peak_equity:
            self.peak_equity = new_equity

        if self.peak_equity > 0:
            dd = (self.peak_equity - new_equity) / self.peak_equity
            if dd > self.max_drawdown:
                self.max_drawdown = dd

        # Track return from last equity point
        if len(self.equity_curve) >= 2:
            prev = self.equity_curve[-2]
            if prev > 0:
                self.returns.append((new_equity - prev) / prev)

        self.timeseries.append(
            {
                "time": (timestamp or datetime.now()).isoformat(),
                "equity": new_equity,
                "pnl": new_equity - self.initial_balance,
                "regime": regime,
            }
        )

    def calculate_win_rate(self, trade_history: List[dict]) -> float:
        """Win rate = winning trades / total trades."""
        if not trade_history:
            return 0.0
        wins = sum(1 for t in trade_history if t.get("net_pnl", t.get("pnl", 0)) > 0)
        return wins / len(trade_history)

    def calculate_max_drawdown(self) -> float:
        """Return current max drawdown as a fraction (0.0 to 1.0)."""
        return self.max_drawdown

    def calculate_sharpe_ratio(
        self, risk_free_rate: float = 0.0, annualize_factor: float = 252.0
    ) -> float:
        """Annualized Sharpe ratio from periodic returns.

        Sharpe = (mean_return - risk_free) / std_return × sqrt(annualize_factor)
        """
        if len(self.returns) < 2:
            return 0.0
        mean_r = sum(self.returns) / len(self.returns)
        variance = sum((r - mean_r) ** 2 for r in self.returns) / (
            len(self.returns) - 1
        )
        std_r = math.sqrt(variance)
        if std_r == 0:
            return 0.0
        return (mean_r - risk_free_rate) * math.sqrt(annualize_factor) / std_r

    def get_summary(self, trade_history: List[dict]) -> dict:
        """Return a full metrics summary."""
        return {
            "win_rate": self.calculate_win_rate(trade_history),
            "max_drawdown": self.calculate_max_drawdown(),
            "sharpe_ratio": self.calculate_sharpe_ratio(),
            "total_return": (
                (self.equity_curve[-1] - self.initial_balance) / self.initial_balance
                if self.equity_curve
                else 0.0
            ),
            "equity_points": len(self.equity_curve),
        }
