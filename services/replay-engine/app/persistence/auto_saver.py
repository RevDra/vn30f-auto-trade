"""Auto-save: hooks into engine events to persist trades + equity snapshots."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.persistence.repository import TradingRepository
from app.constants import CONTRACT_MULTIPLIER

logger = logging.getLogger("replay-engine.autosave")


class AutoSaver:
    """Background auto-save service that persists engine state to the database.

    Features:
    - Saves trades immediately when they close
    - Snapshots equity at configurable intervals (default 60s)
    - Updates session metrics periodically
    """

    def __init__(
        self,
        repo: TradingRepository,
        snapshot_interval: float = 60.0,
    ):
        self._repo = repo
        self._snapshot_interval = snapshot_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_trade_count: dict[str, int] = {}

    async def start(self, session_mgr):
        """Start the background auto-save loop."""
        self._running = True
        self._session_mgr = session_mgr
        self._task = asyncio.create_task(self._loop())
        logger.info("AutoSaver started (interval=%ss)", self._snapshot_interval)

    async def stop(self):
        """Stop the background loop and flush remaining data."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush_all()
        logger.info("AutoSaver stopped")

    async def _loop(self):
        """Periodic loop: snapshot equity + check for new trades."""
        while self._running:
            try:
                await self._flush_all()
            except Exception as e:
                logger.error("AutoSaver error: %s", e)
            await asyncio.sleep(self._snapshot_interval)

    async def _flush_all(self):
        """Flush new trades + equity snapshots for all sessions."""
        if not hasattr(self, "_session_mgr"):
            return

        for info in self._session_mgr.list_sessions():
            sid = info["session_id"]
            engine = self._session_mgr.get_session(sid)
            if engine is None:
                continue

            # Persist new closed trades
            await self._save_new_trades(sid, engine)

            # Snapshot current equity
            await self._snapshot_equity(sid, engine)

            # Update session metrics
            await self._update_metrics(sid, engine)

    async def _save_new_trades(self, session_id: str, engine):
        """Save any trades that haven't been persisted yet."""
        last_count = self._last_trade_count.get(session_id, 0)
        current_trades = engine.trade_history
        new_trades = current_trades[last_count:]

        for trade in new_trades:
            trade_data = {
                "session_id": session_id,
                "entry_time": trade["entry_time"],
                "exit_time": trade.get("exit_time"),
                "direction": trade["type"],
                "volume": trade["volume"],
                "entry_price": trade["entry_price"],
                "exit_price": trade.get("exit_price"),
                "commission": trade.get("commission", 0.0),
                "tax": trade.get("tax", 0.0),
                "gross_pnl": trade.get("gross_pnl"),
                "net_pnl": trade.get("net_pnl"),
                "status": "closed",
            }
            await self._repo.save_trade(trade_data)

        if new_trades:
            self._last_trade_count[session_id] = len(current_trades)
            logger.debug("Saved %d new trades for session '%s'", len(new_trades), session_id)

    async def _snapshot_equity(self, session_id: str, engine):
        """Take an equity snapshot for the session."""
        now = datetime.utcnow()

        # Calculate margin info
        margin_used = 0.0
        margin_available = engine.equity
        if engine.active_position:
            pos = engine.active_position
            margin_used = (
                pos["entry_price"]
                * pos["volume"]
                * CONTRACT_MULTIPLIER
                * engine.margin_mgr.initial_margin
            )
            margin_available = engine.equity - margin_used

        snapshot_data = {
            "session_id": session_id,
            "timestamp": now,
            "equity": round(engine.equity, 2),
            "pnl_realized": round(engine.total_pnl, 2),
            "pnl_unrealized": round(engine.get_unrealized_pnl(), 2),
            "margin_used": round(margin_used, 2),
            "margin_available": round(margin_available, 2),
            "regime": getattr(engine, "_last_regime", None),
            "session_name": engine.session_validator.get_session_name(now),
        }
        await self._repo.save_equity_snapshot(snapshot_data)

    async def _update_metrics(self, session_id: str, engine):
        """Update session metrics in the DB."""
        metrics = engine.metrics.get_summary(engine.trade_history)
        await self._repo.update_session_metrics(
            session_id=session_id,
            final_pnl=round(engine.total_pnl, 2),
            total_trades=len(engine.trade_history),
            win_rate=round(metrics["win_rate"], 4),
            max_drawdown=round(metrics["max_drawdown"], 4),
            sharpe_ratio=round(metrics["sharpe_ratio"], 4),
            total_commission=round(engine.total_commission, 2),
            total_tax=round(engine.total_tax, 2),
        )

    async def on_trade_closed(self, session_id: str, trade: dict):
        """Immediately persist a single closed trade (event-driven hook)."""
        trade_data = {
            "session_id": session_id,
            "entry_time": trade["entry_time"],
            "exit_time": trade.get("exit_time"),
            "direction": trade["type"],
            "volume": trade["volume"],
            "entry_price": trade["entry_price"],
            "exit_price": trade.get("exit_price"),
            "commission": trade.get("commission", 0.0),
            "tax": trade.get("tax", 0.0),
            "gross_pnl": trade.get("gross_pnl"),
            "net_pnl": trade.get("net_pnl"),
            "status": "closed",
        }
        await self._repo.save_trade(trade_data)
        # Update count to avoid double-save in periodic flush
        self._last_trade_count[session_id] = self._last_trade_count.get(session_id, 0) + 1

    async def ensure_session_persisted(self, session_id: str, engine):
        """Ensure a session row exists in the database."""
        existing = await self._repo.get_session(session_id)
        if existing is None:
            await self._repo.create_session(
                session_id=session_id,
                initial_balance=engine.initial_balance,
                strategy=engine.strategy,
            )
