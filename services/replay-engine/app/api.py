"""FastAPI application with expanded endpoints."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import redis.asyncio as aioredis

from app.session import SessionManager
from app.listeners import listen_to_redis
from app.risk import InsufficientMarginError, PriceLimitError, PositionLimitError
from app.constants import DEFAULT_INITIAL_BALANCE

import sys
sys.path.append("/app")

logger = logging.getLogger("replay-engine")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# --- Request/Response Models ---

class OrderRequest(BaseModel):
    action: str = Field(..., pattern="^(LONG|SHORT)$")
    volume: int = Field(..., gt=0, le=500)


class SessionCreateRequest(BaseModel):
    session_id: str = "default"
    strategy: str = "manual"
    initial_balance: float = DEFAULT_INITIAL_BALANCE
    strict_hours: bool = False


class HealthResponse(BaseModel):
    status: str
    redis_connected: bool
    active_sessions: int
    db_connected: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


# --- Globals ---

session_mgr = SessionManager()
redis_client: Optional[aioredis.Redis] = None
background_tasks = set()

# Persistence (Phase 3) — lazy-initialized
_db_manager = None
_repo = None
_auto_saver = None

# Agent system (Phase 4) — lazy-initialized
_tournament_mgr = None
_prediction_sub = None


def _get_redis_config():
    """Get Redis config, try shared.config first, fallback to defaults."""
    try:
        from shared.config import settings
        return settings.REDIS_HOST, settings.REDIS_PORT
    except Exception:
        return os.getenv("REDIS_HOST", "localhost"), int(os.getenv("REDIS_PORT", "6379"))


async def _init_persistence():
    """Initialize database + repository + auto-saver (Phase 3)."""
    global _db_manager, _repo, _auto_saver

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Build from individual env vars (MySQL default, SQLite for tests)
        driver = os.getenv("DB_DRIVER", "")
        if driver:
            db_url = None  # let DatabaseManager build it
        else:
            logger.info("No DATABASE_URL set — persistence disabled")
            return

    try:
        from app.persistence.database import DatabaseManager
        from app.persistence.repository import TradingRepository
        from app.persistence.auto_saver import AutoSaver
        from app.persistence.history_api import init_history_router, router as history_router

        _db_manager = DatabaseManager(url=db_url)
        await _db_manager.init()

        _repo = TradingRepository(_db_manager)
        _auto_saver = AutoSaver(_repo, snapshot_interval=60.0)

        # Register history router
        init_history_router(_repo)
        app.include_router(history_router)

        # Persist existing sessions
        for info in session_mgr.list_sessions():
            engine = session_mgr.get_session(info["session_id"])
            if engine:
                await _auto_saver.ensure_session_persisted(info["session_id"], engine)

        # Start background auto-save
        await _auto_saver.start(session_mgr)
        logger.info("Persistence layer initialized")
    except Exception as e:
        logger.warning("Persistence init failed (non-fatal): %s", e)
        _db_manager = None
        _repo = None
        _auto_saver = None


def _init_agents():
    """Initialize agent system (Phase 4)."""
    global _tournament_mgr, _prediction_sub
    try:
        from app.agents.agent_api import init_agent_router, router as agent_router
        _tournament_mgr = init_agent_router(session_mgr)
        app.include_router(agent_router)
        logger.info("Agent system initialized")
    except Exception as e:
        logger.warning("Agent system init failed (non-fatal): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    host, port = _get_redis_config()

    try:
        redis_client = aioredis.Redis(host=host, port=port, decode_responses=True)
        await redis_client.ping()
        logger.info(f"Connected to Redis at {host}:{port}")

        task = asyncio.create_task(listen_to_redis(redis_client, session_mgr))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        redis_client = None

    # Create default session if none exists
    if not session_mgr.list_sessions():
        session_mgr.create_session("default")

    # Initialize persistence (Phase 3)
    await _init_persistence()

    # Initialize agent system (Phase 4)
    _init_agents()

    yield

    # Shutdown auto-saver
    if _auto_saver:
        await _auto_saver.stop()

    for task in background_tasks:
        task.cancel()
    if redis_client:
        await redis_client.close()

    # Close DB
    if _db_manager:
        await _db_manager.close()


app = FastAPI(
    title="Replay Engine (Mock Exchange)",
    version="2.0.0",
    lifespan=lifespan,
)


def _get_engine():
    """Get active engine or raise 404."""
    engine = session_mgr.get_active_engine()
    if engine is None:
        raise HTTPException(404, "No active session")
    return engine


# --- Health ---

@app.get("/health", response_model=HealthResponse)
async def health():
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass
    db_ok = _db_manager is not None and _db_manager._engine is not None
    return HealthResponse(
        status="ok" if redis_ok else "degraded",
        redis_connected=redis_ok,
        active_sessions=len(session_mgr.list_sessions()),
        db_connected=db_ok,
    )


# --- PnL / State ---

@app.get("/api/v1/pnl")
def get_pnl():
    engine = _get_engine()
    state = engine.get_state()
    metrics_summary = engine.metrics.get_summary(engine.trade_history)

    active_pos = None
    if engine.active_position:
        active_pos = {
            "type": engine.active_position["type"],
            "volume": engine.active_position["volume"],
            "entry_price": engine.active_position["entry_price"],
            "current_price": engine.current_price,
            "unrealized_pnl": round(engine.get_unrealized_pnl(), 2),
        }

    return {
        "timestamp": datetime.now().isoformat(),
        "symbol": "VN30F1M",
        "session_id": engine.session_id,
        "balance": state["balance"],
        "equity": state["equity"],
        "session_summary": {
            "total_trades": state["total_trades"],
            "win_rate": round(metrics_summary["win_rate"], 4),
            "pnl_vnd": round(state["total_pnl"], 2),
            "max_drawdown_percent": round(metrics_summary["max_drawdown"] * 100, 2),
            "sharpe_ratio": round(metrics_summary["sharpe_ratio"], 4),
            "total_commission": round(state["total_commission"], 2),
            "total_tax": round(state["total_tax"], 2),
        },
        "active_position": active_pos,
    }


# --- Orders ---

@app.post("/api/v1/order")
async def place_order(req: OrderRequest):
    engine = _get_engine()
    try:
        result = engine.place_order(req.action, req.volume)
        # Auto-save closed trade if persistence is active
        if _auto_saver and result.get("action") == "CLOSE" and engine.trade_history:
            last_trade = engine.trade_history[-1]
            await _auto_saver.on_trade_closed(engine.session_id, last_trade)
        return {"status": "ok", **result}
    except InsufficientMarginError as e:
        raise HTTPException(422, str(e))
    except (PriceLimitError, PositionLimitError) as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/close-position")
async def close_position():
    engine = _get_engine()
    result = engine.close_position()
    if result is None:
        raise HTTPException(400, "No active position to close")
    # Auto-save the closed trade
    if _auto_saver and engine.trade_history:
        last_trade = engine.trade_history[-1]
        await _auto_saver.on_trade_closed(engine.session_id, last_trade)
    return {"status": "ok", **result}


# --- Trades / Equity ---

@app.get("/api/v1/trades")
def get_trades(page: int = 1, page_size: int = 50):
    engine = _get_engine()
    trades = engine.trade_history
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": len(trades),
        "page": page,
        "page_size": page_size,
        "trades": trades[start:end],
    }


@app.get("/api/v1/equity-curve")
def get_equity_curve():
    engine = _get_engine()
    return {
        "session_id": engine.session_id,
        "initial_balance": engine.initial_balance,
        "points": len(engine.metrics.equity_curve),
        "equity_curve": engine.metrics.equity_curve[-500:],
        "timeseries": engine.metrics.timeseries[-500:],
    }


# --- Session Management ---

@app.get("/api/v1/sessions")
def list_sessions():
    return {"sessions": session_mgr.list_sessions()}


@app.post("/api/v1/sessions")
async def create_session(req: SessionCreateRequest):
    try:
        engine = session_mgr.create_session(
            session_id=req.session_id,
            strategy=req.strategy,
            initial_balance=req.initial_balance,
            strict_hours=req.strict_hours,
        )
        # Persist to DB if available
        if _auto_saver:
            await _auto_saver.ensure_session_persisted(req.session_id, engine)
        return {"status": "ok", "session_id": engine.session_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/v1/sessions/{session_id}/activate")
def activate_session(session_id: str):
    try:
        session_mgr.switch_session(session_id)
        return {"status": "ok", "active_session": session_id}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str):
    if not session_mgr.delete_session(session_id):
        raise HTTPException(404, f"Session '{session_id}' not found")
    return {"status": "ok", "deleted": session_id}


# --- Reset ---

@app.post("/api/v1/reset")
def reset_engine():
    engine = _get_engine()
    engine.reset()
    return {"status": "ok", "message": "Engine reset to initial state"}
