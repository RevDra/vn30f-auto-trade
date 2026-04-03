"""SQLAlchemy ORM models matching the VN30F MySQL schema."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.database import Base


class TradingSessionModel(Base):
    __tablename__ = "trading_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    strategy: Mapped[str] = mapped_column(String(100), default="manual")
    initial_balance: Mapped[float] = mapped_column(Float, nullable=False)
    final_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    total_commission: Mapped[float] = mapped_column(Float, default=0.0)
    total_tax: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        Enum("active", "completed", "cancelled", name="session_status"),
        default="active",
    )

    # Relationships
    trades: Mapped[list["TradeModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    equity_snapshots: Mapped[list["EquitySnapshotModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "strategy": self.strategy,
            "initial_balance": self.initial_balance,
            "final_pnl": self.final_pnl,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "total_commission": self.total_commission,
            "total_tax": self.total_tax,
            "status": self.status,
        }


class TradeModel(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trading_sessions.id", ondelete="CASCADE"), nullable=False
    )
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    direction: Mapped[str] = mapped_column(
        Enum("LONG", "SHORT", name="trade_direction"), nullable=False
    )
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_entry: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_exit: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    gross_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("open", "closed", name="trade_status"), nullable=False
    )

    session: Mapped["TradingSessionModel"] = relationship(back_populates="trades")

    __table_args__ = (
        Index("idx_session_direction", "session_id", "direction"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "direction": self.direction,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "slippage_entry": self.slippage_entry,
            "slippage_exit": self.slippage_exit,
            "commission": self.commission,
            "tax": self.tax,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "status": self.status,
        }


class EquitySnapshotModel(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trading_sessions.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_realized: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_unrealized: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    margin_used: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    margin_available: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    regime: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    session_name: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    session: Mapped["TradingSessionModel"] = relationship(back_populates="equity_snapshots")

    __table_args__ = (
        Index("idx_session_time", "session_id", "timestamp"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "equity": self.equity,
            "pnl_realized": self.pnl_realized,
            "pnl_unrealized": self.pnl_unrealized,
            "margin_used": self.margin_used,
            "margin_available": self.margin_available,
            "regime": self.regime,
            "session_name": self.session_name,
        }
