"""Session history API endpoints — Phase 3d."""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.persistence.database import DatabaseManager
from app.persistence.repository import TradingRepository

logger = logging.getLogger("replay-engine.history")

router = APIRouter(prefix="/api/v1/history", tags=["history"])

# Will be set during app startup
_repo: Optional[TradingRepository] = None


def init_history_router(repo: TradingRepository):
    """Initialize the history router with a repository instance."""
    global _repo
    _repo = repo


def _get_repo() -> TradingRepository:
    if _repo is None:
        raise HTTPException(503, "Persistence layer not available")
    return _repo


@router.get("/sessions")
async def list_past_sessions(
    status: Optional[str] = Query(None, pattern="^(active|completed|cancelled)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all persisted sessions with their metrics."""
    repo = _get_repo()
    sessions = await repo.list_sessions(status=status, limit=limit, offset=offset)
    total = await repo.count_sessions(status=status)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sessions": [s.to_dict() for s in sessions],
    }


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get detailed info for a specific session including trade stats."""
    repo = _get_repo()
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session '{session_id}' not found")

    trade_stats = await repo.get_session_trade_stats(session_id)
    data = session.to_dict()
    data["trade_stats"] = trade_stats
    return data


@router.get("/sessions/{session_id}/trades")
async def get_session_trades(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Get paginated trade history for a session."""
    repo = _get_repo()
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session '{session_id}' not found")

    trades, total = await repo.get_trades(session_id, page=page, page_size=page_size)
    return {
        "session_id": session_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "trades": [t.to_dict() for t in trades],
    }


@router.get("/sessions/{session_id}/equity-curve")
async def get_session_equity_curve(
    session_id: str,
    limit: int = Query(500, ge=1, le=5000),
):
    """Get equity curve snapshots for a session."""
    repo = _get_repo()
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session '{session_id}' not found")

    snapshots = await repo.get_equity_curve(session_id, limit=limit)
    return {
        "session_id": session_id,
        "initial_balance": session.initial_balance,
        "points": len(snapshots),
        "snapshots": [snap.to_dict() for snap in snapshots],
    }


@router.post("/sessions/compare")
async def compare_sessions(session_ids: List[str]):
    """Compare metrics across multiple sessions side-by-side."""
    if len(session_ids) < 2:
        raise HTTPException(400, "At least 2 session IDs required for comparison")
    if len(session_ids) > 10:
        raise HTTPException(400, "Max 10 sessions for comparison")

    repo = _get_repo()
    results = await repo.compare_sessions(session_ids)

    found_ids = {r["id"] for r in results}
    missing = [sid for sid in session_ids if sid not in found_ids]

    return {
        "sessions": results,
        "missing": missing,
    }
