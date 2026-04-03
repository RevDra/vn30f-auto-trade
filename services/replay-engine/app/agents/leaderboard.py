"""Leaderboard calculator — ranking agents by multiple metrics."""

import logging
from typing import List, Optional
from enum import Enum

from app.agents.agent_manager import AgentManager

logger = logging.getLogger("replay-engine.leaderboard")


class SortMetric(str, Enum):
    PNL = "pnl"
    WIN_RATE = "win_rate"
    SHARPE = "sharpe_ratio"
    DRAWDOWN = "max_drawdown"
    TRADES = "total_trades"
    EQUITY = "equity"


class LeaderboardCalculator:
    """Calculates and ranks agent performance."""

    def __init__(self, agent_mgr: AgentManager):
        self._agent_mgr = agent_mgr

    def get_leaderboard(
        self,
        sort_by: SortMetric = SortMetric.PNL,
        ascending: bool = False,
        top_n: Optional[int] = None,
    ) -> List[dict]:
        """Generate ranked leaderboard of all agents."""
        entries = []

        for agent_id in self._agent_mgr.get_agent_ids():
            config = self._agent_mgr.get_agent_config(agent_id)
            engine = self._agent_mgr.get_agent_engine(agent_id)
            if config is None or engine is None:
                continue

            metrics = engine.metrics.get_summary(engine.trade_history)
            entry = {
                "rank": 0,
                "agent_id": agent_id,
                "name": config.name,
                "strategy": config.strategy,
                "balance": round(engine.balance, 2),
                "equity": round(engine.equity, 2),
                "pnl": round(engine.total_pnl, 2),
                "pnl_percent": round(
                    (engine.total_pnl / config.initial_balance) * 100, 2
                ) if config.initial_balance else 0.0,
                "total_trades": len(engine.trade_history),
                "win_rate": round(metrics["win_rate"] * 100, 2),
                "max_drawdown": round(metrics["max_drawdown"] * 100, 2),
                "sharpe_ratio": round(metrics["sharpe_ratio"], 4),
                "total_commission": round(engine.total_commission, 2),
                "total_tax": round(engine.total_tax, 2),
                "has_position": engine.active_position is not None,
            }
            entries.append(entry)

        # Sort
        sort_key = self._get_sort_key(sort_by)
        reverse = not ascending
        # For drawdown, lower is better (ascending)
        if sort_by == SortMetric.DRAWDOWN:
            reverse = ascending

        entries.sort(key=lambda e: e.get(sort_key, 0), reverse=reverse)

        # Assign ranks
        for i, entry in enumerate(entries, 1):
            entry["rank"] = i

        if top_n:
            entries = entries[:top_n]

        return entries

    def get_agent_stats(self, agent_id: str) -> Optional[dict]:
        """Get detailed stats for a single agent."""
        config = self._agent_mgr.get_agent_config(agent_id)
        engine = self._agent_mgr.get_agent_engine(agent_id)
        if config is None or engine is None:
            return None

        metrics = engine.metrics.get_summary(engine.trade_history)
        state = engine.get_state()

        return {
            "agent_id": agent_id,
            "name": config.name,
            "strategy": config.strategy,
            "config": config.to_dict(),
            "state": state,
            "metrics": metrics,
            "trade_count": len(engine.trade_history),
            "recent_trades": engine.trade_history[-10:],
        }

    @staticmethod
    def _get_sort_key(metric: SortMetric) -> str:
        mapping = {
            SortMetric.PNL: "pnl",
            SortMetric.WIN_RATE: "win_rate",
            SortMetric.SHARPE: "sharpe_ratio",
            SortMetric.DRAWDOWN: "max_drawdown",
            SortMetric.TRADES: "total_trades",
            SortMetric.EQUITY: "equity",
        }
        return mapping.get(metric, "pnl")
