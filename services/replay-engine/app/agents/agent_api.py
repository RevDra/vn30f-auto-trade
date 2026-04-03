"""Agent API endpoints — Phase 4."""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.session import SessionManager
from app.agents.agent_manager import AgentManager, AgentConfig
from app.agents.subscriber import PredictionSubscriber
from app.agents.leaderboard import LeaderboardCalculator, SortMetric
from app.agents.tournament import TournamentManager, TournamentConfig, TournamentStatus
from app.constants import DEFAULT_INITIAL_BALANCE

logger = logging.getLogger("replay-engine.agent-api")

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# Will be set during app startup
_tournament_mgr: Optional[TournamentManager] = None
_subscriber: Optional[PredictionSubscriber] = None


# ── Request Models ───────────────────────────────────────────

class AgentRegisterRequest(BaseModel):
    agent_id: str
    name: str
    strategy: str = "ai"
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    max_volume: int = Field(10, gt=0, le=500)


class AgentOrderRequest(BaseModel):
    action: str = Field(..., pattern="^(LONG|SHORT)$")
    volume: int = Field(1, gt=0, le=500)
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class TournamentCreateRequest(BaseModel):
    name: str
    initial_balance: float = DEFAULT_INITIAL_BALANCE
    max_agents: int = Field(20, gt=0, le=100)


class PredictionRequest(BaseModel):
    agent_id: str
    action: str
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    volume: int = Field(1, gt=0, le=500)


# ── Init ─────────────────────────────────────────────────────

def init_agent_router(session_mgr: SessionManager) -> TournamentManager:
    """Initialize the agent system with tournament + subscriber."""
    global _tournament_mgr, _subscriber
    _tournament_mgr = TournamentManager(session_mgr)
    _subscriber = PredictionSubscriber(_tournament_mgr.agent_manager)
    return _tournament_mgr


def get_tournament_mgr() -> TournamentManager:
    if _tournament_mgr is None:
        raise HTTPException(503, "Agent system not initialized")
    return _tournament_mgr


def get_subscriber() -> PredictionSubscriber:
    if _subscriber is None:
        raise HTTPException(503, "Agent system not initialized")
    return _subscriber


# ── Agent CRUD ───────────────────────────────────────────────

@router.post("/register")
def register_agent(req: AgentRegisterRequest):
    tmgr = get_tournament_mgr()
    config = AgentConfig(
        agent_id=req.agent_id,
        name=req.name,
        strategy=req.strategy,
        confidence_threshold=req.confidence_threshold,
        max_volume=req.max_volume,
    )
    try:
        # If tournament is active, use tournament's add_agent (enforces balance + max_agents)
        if tmgr._config is not None:
            result = tmgr.add_agent(config)
        else:
            # Direct registration without tournament
            engine = tmgr.agent_manager.register_agent(config)
            result = {
                "agent_id": config.agent_id,
                "session_id": engine.session_id,
                "initial_balance": config.initial_balance,
            }
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{agent_id}")
def unregister_agent(agent_id: str):
    tmgr = get_tournament_mgr()
    removed = tmgr.agent_manager.unregister_agent(agent_id)
    if not removed:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return {"status": "ok", "removed": agent_id}


@router.get("/")
def list_agents():
    tmgr = get_tournament_mgr()
    return {"agents": tmgr.agent_manager.list_agents()}


@router.get("/{agent_id}")
def get_agent(agent_id: str):
    tmgr = get_tournament_mgr()
    stats = tmgr.leaderboard.get_agent_stats(agent_id)
    if stats is None:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return stats


# ── Agent Orders ─────────────────────────────────────────────

@router.post("/{agent_id}/order")
def agent_order(agent_id: str, req: AgentOrderRequest):
    tmgr = get_tournament_mgr()
    config = tmgr.agent_manager.get_agent_config(agent_id)
    if config is None:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    if req.confidence < config.confidence_threshold:
        return {
            "status": "rejected",
            "reason": f"Confidence {req.confidence} < threshold {config.confidence_threshold}",
        }

    try:
        result = tmgr.agent_manager.place_agent_order(agent_id, req.action, req.volume)
        return {"status": "ok", "agent_id": agent_id, **result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{agent_id}/close")
def agent_close(agent_id: str):
    tmgr = get_tournament_mgr()
    engine = tmgr.agent_manager.get_agent_engine(agent_id)
    if engine is None:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    result = engine.close_position()
    if result is None:
        raise HTTPException(400, "No active position")
    return {"status": "ok", "agent_id": agent_id, **result}


# ── Prediction Endpoint (direct, without Redis) ─────────────

@router.post("/predict")
def submit_prediction(req: PredictionRequest):
    """Submit a prediction directly (alternative to Redis pub/sub)."""
    sub = get_subscriber()
    result = sub.process_prediction_sync({
        "agent_id": req.agent_id,
        "action": req.action,
        "confidence": req.confidence,
        "volume": req.volume,
    })
    return result


@router.get("/predict/stats")
def prediction_stats():
    sub = get_subscriber()
    return sub.stats


# ── Leaderboard ──────────────────────────────────────────────

@router.get("/leaderboard/rankings")
def get_leaderboard(
    sort_by: str = Query("pnl", pattern="^(pnl|win_rate|sharpe_ratio|max_drawdown|total_trades|equity)$"),
    ascending: bool = False,
    top_n: Optional[int] = Query(None, ge=1, le=100),
):
    tmgr = get_tournament_mgr()
    metric = SortMetric(sort_by)
    entries = tmgr.leaderboard.get_leaderboard(
        sort_by=metric,
        ascending=ascending,
        top_n=top_n,
    )
    return {"sort_by": sort_by, "ascending": ascending, "entries": entries}


# ── Tournament Control ───────────────────────────────────────

@router.post("/tournament/create")
def create_tournament(req: TournamentCreateRequest):
    tmgr = get_tournament_mgr()
    try:
        config = TournamentConfig(
            name=req.name,
            initial_balance=req.initial_balance,
            max_agents=req.max_agents,
        )
        tmgr.create_tournament(config)
        return {"status": "ok", "tournament": req.name}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/tournament/start")
def start_tournament():
    tmgr = get_tournament_mgr()
    try:
        tmgr.start()
        return {"status": "ok", "message": "Tournament started"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/tournament/pause")
def pause_tournament():
    tmgr = get_tournament_mgr()
    try:
        tmgr.pause()
        return {"status": "ok", "message": "Tournament paused"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/tournament/resume")
def resume_tournament():
    tmgr = get_tournament_mgr()
    try:
        tmgr.resume()
        return {"status": "ok", "message": "Tournament resumed"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/tournament/stop")
def stop_tournament():
    tmgr = get_tournament_mgr()
    try:
        tmgr.stop()
        return {"status": "ok", "message": "Tournament completed"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/tournament/standings")
def tournament_standings(
    sort_by: str = Query("pnl", pattern="^(pnl|win_rate|sharpe_ratio|max_drawdown|total_trades|equity)$"),
):
    tmgr = get_tournament_mgr()
    metric = SortMetric(sort_by)
    return tmgr.get_standings(sort_by=metric)


@router.get("/tournament/state")
def tournament_state():
    tmgr = get_tournament_mgr()
    return tmgr.get_state()
