"""Async CRUD repository for all persistence operations."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import DatabaseManager
from app.persistence.models import (
    TradingSessionModel,
    TradeModel,
    EquitySnapshotModel,
)

logger = logging.getLogger("replay-engine.repo")


class TradingRepository:
    """Async CRUD operations for trading persistence."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    # ── Session CRUD ──────────────────────────────────────────

    async def create_session(
        self,
        session_id: str,
        initial_balance: float,
        strategy: str = "manual",
    ) -> TradingSessionModel:
        async with self._db.session() as s:
            model = TradingSessionModel(
                id=session_id,
                started_at=datetime.now(timezone.utc),
                initial_balance=initial_balance,
                strategy=strategy,
                status="active",
            )
            s.add(model)
            await s.commit()
            await s.refresh(model)
            logger.info("Persisted session '%s'", session_id)
            return model

    async def get_session(self, session_id: str) -> Optional[TradingSessionModel]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TradingSessionModel).where(TradingSessionModel.id == session_id)
            )
            return result.scalar_one_or_none()

    async def update_session_metrics(
        self,
        session_id: str,
        final_pnl: float,
        total_trades: int,
        win_rate: float,
        max_drawdown: float,
        sharpe_ratio: float,
        total_commission: float,
        total_tax: float,
    ):
        async with self._db.session() as s:
            result = await s.execute(
                select(TradingSessionModel).where(TradingSessionModel.id == session_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                return
            model.final_pnl = final_pnl
            model.total_trades = total_trades
            model.win_rate = win_rate
            model.max_drawdown = max_drawdown
            model.sharpe_ratio = sharpe_ratio
            model.total_commission = total_commission
            model.total_tax = total_tax
            await s.commit()

    async def complete_session(self, session_id: str):
        async with self._db.session() as s:
            result = await s.execute(
                select(TradingSessionModel).where(TradingSessionModel.id == session_id)
            )
            model = result.scalar_one_or_none()
            if model:
                model.status = "completed"
                model.ended_at = datetime.now(timezone.utc)
                await s.commit()

    async def list_sessions(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TradingSessionModel]:
        async with self._db.session() as s:
            q = select(TradingSessionModel).order_by(desc(TradingSessionModel.started_at))
            if status:
                q = q.where(TradingSessionModel.status == status)
            q = q.limit(limit).offset(offset)
            result = await s.execute(q)
            return list(result.scalars().all())

    async def count_sessions(self, status: Optional[str] = None) -> int:
        async with self._db.session() as s:
            q = select(func.count()).select_from(TradingSessionModel)
            if status:
                q = q.where(TradingSessionModel.status == status)
            result = await s.execute(q)
            return result.scalar() or 0

    async def delete_session(self, session_id: str) -> bool:
        async with self._db.session() as s:
            result = await s.execute(
                select(TradingSessionModel).where(TradingSessionModel.id == session_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                return False
            await s.delete(model)
            await s.commit()
            return True

    # ── Trade CRUD ────────────────────────────────────────────

    async def save_trade(self, trade_data: dict) -> TradeModel:
        async with self._db.session() as s:
            model = TradeModel(
                session_id=trade_data["session_id"],
                entry_time=_parse_dt(trade_data["entry_time"]),
                exit_time=_parse_dt(trade_data.get("exit_time")),
                direction=trade_data["direction"],
                volume=trade_data["volume"],
                entry_price=trade_data["entry_price"],
                exit_price=trade_data.get("exit_price"),
                slippage_entry=trade_data.get("slippage_entry", 0.0),
                slippage_exit=trade_data.get("slippage_exit", 0.0),
                commission=trade_data.get("commission", 0.0),
                tax=trade_data.get("tax", 0.0),
                gross_pnl=trade_data.get("gross_pnl"),
                net_pnl=trade_data.get("net_pnl"),
                status=trade_data.get("status", "closed"),
            )
            s.add(model)
            await s.commit()
            await s.refresh(model)
            return model

    async def get_trades(
        self,
        session_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[TradeModel], int]:
        """Return (trades, total_count) for a session."""
        async with self._db.session() as s:
            count_q = (
                select(func.count())
                .select_from(TradeModel)
                .where(TradeModel.session_id == session_id)
            )
            total = (await s.execute(count_q)).scalar() or 0

            q = (
                select(TradeModel)
                .where(TradeModel.session_id == session_id)
                .order_by(desc(TradeModel.entry_time))
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
            result = await s.execute(q)
            return list(result.scalars().all()), total

    async def get_session_trade_stats(self, session_id: str) -> dict:
        """Aggregate trade stats for a session."""
        async with self._db.session() as s:
            q = select(
                func.count().label("total"),
                func.sum(TradeModel.net_pnl).label("total_pnl"),
                func.sum(TradeModel.commission).label("total_commission"),
                func.sum(TradeModel.tax).label("total_tax"),
            ).where(TradeModel.session_id == session_id)
            row = (await s.execute(q)).one()
            return {
                "total_trades": row.total or 0,
                "total_pnl": float(row.total_pnl or 0),
                "total_commission": float(row.total_commission or 0),
                "total_tax": float(row.total_tax or 0),
            }

    # ── Equity Snapshots ──────────────────────────────────────

    async def save_equity_snapshot(self, snapshot_data: dict) -> EquitySnapshotModel:
        async with self._db.session() as s:
            model = EquitySnapshotModel(
                session_id=snapshot_data["session_id"],
                timestamp=_parse_dt(snapshot_data["timestamp"]),
                equity=snapshot_data["equity"],
                pnl_realized=snapshot_data.get("pnl_realized"),
                pnl_unrealized=snapshot_data.get("pnl_unrealized"),
                margin_used=snapshot_data.get("margin_used"),
                margin_available=snapshot_data.get("margin_available"),
                regime=snapshot_data.get("regime"),
                session_name=snapshot_data.get("session_name"),
            )
            s.add(model)
            await s.commit()
            await s.refresh(model)
            return model

    async def save_equity_snapshots_bulk(self, snapshots: List[dict]):
        """Bulk insert equity snapshots for efficiency."""
        if not snapshots:
            return
        async with self._db.session() as s:
            models = [
                EquitySnapshotModel(
                    session_id=snap["session_id"],
                    timestamp=_parse_dt(snap["timestamp"]),
                    equity=snap["equity"],
                    pnl_realized=snap.get("pnl_realized"),
                    pnl_unrealized=snap.get("pnl_unrealized"),
                    margin_used=snap.get("margin_used"),
                    margin_available=snap.get("margin_available"),
                    regime=snap.get("regime"),
                    session_name=snap.get("session_name"),
                )
                for snap in snapshots
            ]
            s.add_all(models)
            await s.commit()

    async def get_equity_curve(
        self,
        session_id: str,
        limit: int = 500,
    ) -> List[EquitySnapshotModel]:
        async with self._db.session() as s:
            q = (
                select(EquitySnapshotModel)
                .where(EquitySnapshotModel.session_id == session_id)
                .order_by(desc(EquitySnapshotModel.timestamp))
                .limit(limit)
            )
            result = await s.execute(q)
            snapshots = list(result.scalars().all())
            snapshots.reverse()  # chronological order
            return snapshots

    # ── Session Comparison ────────────────────────────────────

    async def compare_sessions(self, session_ids: List[str]) -> List[dict]:
        """Return side-by-side metrics for multiple sessions."""
        async with self._db.session() as s:
            q = select(TradingSessionModel).where(
                TradingSessionModel.id.in_(session_ids)
            )
            result = await s.execute(q)
            sessions = list(result.scalars().all())
            return [sess.to_dict() for sess in sessions]


def _parse_dt(val) -> Optional[datetime]:
    """Parse datetime from string or pass-through datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))
